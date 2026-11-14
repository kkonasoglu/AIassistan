"""Dağınık anlatımı düzenleme: "yalnızca böl" doğrulaması ve kural tabanlı yedek.
Canlı denemelerde görülen gerçek hatalar kalıcı test olarak buradadır."""
import unittest
from unittest.mock import patch

from app.services import learning

INFO = ("KNK-500 yazıcı bağlanmıyor. Önce kabloyu kontrol et sonra servisi yeniden başlat "
        "en son bilgisayarı kapatıp aç")
NO_PUNCT = ("e-fatura gönderirken vergi numarası hatası çıkıyor müşteri kartına gidip vergi "
            "numarasını kontrol et 10 veya 11 hane olmalı sonra faturayı tekrar gönder")
PRINTER = ("yazıcı bağlanmıyor KNK-500 hatası veriyor önce yazıcının kablosunu kontrol edin sonra "
           "yazıcı servisini yeniden başlatın en son bilgisayarı kapatıp açın")


def run(raw, text):
    with patch("app.services.llm.complete_text", return_value=raw):
        return learning.structure(text)


class SplitValidation(unittest.TestCase):
    def test_pure_split_is_accepted_and_cleaned(self):
        s = run("KNK-500 yazıcı bağlanmıyor | Önce kabloyu kontrol et | sonra servisi yeniden başlat | "
                "en son bilgisayarı kapatıp aç", INFO)
        self.assertEqual(s["by"], "ai")
        self.assertEqual(s["title"], "KNK-500: Yazıcı bağlanmıyor")
        self.assertEqual(s["solution"], "Çözüm adımları:\n1. Kabloyu kontrol et.\n"
                                        "2. Servisi yeniden başlat.\n3. Bilgisayarı kapatıp aç.")

    def test_unpunctuated_speech_is_split_without_losing_anything(self):
        s = run("e-fatura gönderirken vergi numarası hatası çıkıyor | müşteri kartına gidip vergi numarasını "
                "kontrol et | 10 veya 11 hane olmalı | sonra faturayı tekrar gönder", NO_PUNCT)
        self.assertEqual(s["by"], "ai")
        self.assertEqual(s["title"], "E-fatura gönderirken vergi numarası hatası çıkıyor")
        self.assertIn("1. Müşteri kartına gidip vergi numarasını kontrol et.", s["solution"])
        self.assertIn("2. 10 veya 11 hane olmalı.", s["solution"])       # bilgi kaybolmadı
        self.assertIn("3. Faturayı tekrar gönder.", s["solution"])

    def test_real_model_style_output_with_label_and_quotes(self):
        s = run('Cevap: "KNK-500 yazıcı bağlanmıyor | önce kabloyu kontrol et | sonra servisi yeniden '
                'başlat | en son bilgisayarı kapatıp aç"', INFO)
        self.assertEqual(s["by"], "ai")

    def test_code_goes_to_title_even_when_not_in_first_part(self):
        s = run("yazıcı bağlanmıyor | kabloyu kontrol et | servisi yeniden başlat | bilgisayarı kapatıp aç "
                "| KNK-500", "yazıcı bağlanmıyor kabloyu kontrol et servisi yeniden başlat "
                            "bilgisayarı kapatıp aç KNK-500")
        self.assertEqual(s["title"], "KNK-500: Yazıcı bağlanmıyor")

    def test_changed_word_is_rejected(self):
        # Gerçek denemeler: model "başlatın"/"kontrol edin" gibi kelimeleri kendi biçimine çevirdi
        s = run("KNK-500 yazıcı bağlanmıyor | önce kabloyu kontrol edin | servisi yeniden başlatın | "
                "bilgisayarı kapatıp açın", INFO)
        self.assertEqual(s["by"], "basic")

    def test_invented_step_is_rejected(self):
        # Gerçek denemede model, anlatılmayan bir adım ekledi
        s = run("e-fatura gönderirken vergi numarası hatası çıkıyor | müşteri kartına gidip vergi "
                "numarasını kontrol et | vergi numarasının uzunluğunu kontrol et | 10 veya 11 hane "
                "olmalı | faturayı tekrar gönder", NO_PUNCT)
        self.assertEqual(s["by"], "basic")
        self.assertNotIn("uzunluğunu", s["solution"])

    def test_dropped_information_is_rejected(self):
        # Gerçek denemede model "akıllı kart sürücüsü kurulu mu bak" adımını atladı
        text = ("mali mühür takılı ama program görmüyor önce usb portunu değiştir akıllı kart "
                "sürücüsü kurulu mu bak sonra bilgisayarı yeniden başlat")
        s = run("mali mühür takılı ama program görmüyor | usb portunu değiştir | bilgisayarı yeniden başlat", text)
        self.assertEqual(s["by"], "basic")
        self.assertIn("sürücüsü", " ".join([s["title"], s["solution"]]).lower())   # yedek yöntem bilgiyi korur

    def test_reordered_text_is_rejected(self):
        s = run("KNK-500 yazıcı bağlanmıyor | servisi yeniden başlat | kabloyu kontrol et | "
                "bilgisayarı kapatıp aç", INFO)
        self.assertEqual(s["by"], "basic")

    def test_no_split_or_garbage_falls_back(self):
        for raw in ("KNK-500 yazıcı bağlanmıyor önce kabloyu kontrol et", "bu bir cevap değil", "", "|||"):
            self.assertEqual(run(raw, INFO)["by"], "basic", raw)

    def test_model_failure_falls_back(self):
        with patch("app.services.llm.complete_text", side_effect=ConnectionError("ollama kapalı")):
            self.assertEqual(learning.structure(INFO)["by"], "basic")

    def test_sequence_words_do_not_cause_false_rejection(self):
        # Model "önce/sonra"yı taşıyabilir ya da atabilir; ikisi de kabul
        a = run("KNK-500 yazıcı bağlanmıyor | kabloyu kontrol et | servisi yeniden başlat | "
                "bilgisayarı kapatıp aç", INFO)
        b = run("KNK-500 yazıcı bağlanmıyor | önce kabloyu kontrol et | sonra servisi yeniden başlat | "
                "en son bilgisayarı kapatıp aç", INFO)
        self.assertEqual((a["by"], b["by"]), ("ai", "ai"))
        self.assertEqual(a["solution"], b["solution"])


class SequenceSplitting(unittest.TestCase):
    def test_two_steps_squeezed_into_one_are_separated(self):
        # Gerçek denemede model "10 veya 11 hane olmalı sonra faturayı tekrar gönder" demişti
        s = run("e-fatura gönderirken vergi numarası hatası çıkıyor | müşteri kartına gidip vergi numarasını "
                "kontrol et | 10 veya 11 hane olmalı sonra faturayı tekrar gönder", NO_PUNCT)
        self.assertEqual(s["by"], "ai")
        self.assertEqual(s["solution"].splitlines()[1:],
                         ["1. Müşteri kartına gidip vergi numarasını kontrol et.",
                          "2. 10 veya 11 hane olmalı.", "3. Faturayı tekrar gönder."])

    def test_time_meaning_of_sonra_is_not_a_step_separator(self):
        self.assertEqual(learning._split_sequence("numarayı doğruladıktan sonra faturayı gönder"),
                         ["numarayı doğruladıktan sonra faturayı gönder"])
        self.assertEqual(learning._split_sequence("kabloyu çek bekleyip sonra tak"),
                         ["kabloyu çek bekleyip", "tak"])
        self.assertEqual(learning._split_sequence("kabloyu çek sonra tak ardından yeniden başlat en son test et"),
                         ["kabloyu çek", "tak", "yeniden başlat", "test et"])


class BasicFallback(unittest.TestCase):
    def test_splits_connectors_and_moves_code_to_title(self):
        title, steps = learning.basic_structure(INFO)
        self.assertEqual(title, "KNK-500: Yazıcı bağlanmıyor")
        self.assertEqual(steps, ["Kabloyu kontrol et.", "Servisi yeniden başlat.", "Bilgisayarı kapatıp aç."])

    def test_keeps_existing_numbering_and_lines(self):
        text = "KNK-501 ekran siyah\n1. Kabloyu çek\n2. Tekrar tak\n3. Bilgisayarı yeniden başlat"
        title, steps = learning.basic_structure(text)
        self.assertEqual(title, "KNK-501: Ekran siyah")
        self.assertEqual(steps, ["Kabloyu çek.", "Tekrar tak.", "Bilgisayarı yeniden başlat."])
        _, steps = learning.basic_structure("Ekran siyah 1. kabloyu çek 2. tekrar tak")
        self.assertEqual(steps, ["Kabloyu çek.", "Tekrar tak."])

    def test_without_code_and_single_sentence(self):
        title, steps = learning.basic_structure("yazıcı çıktı vermiyor. kağıt tepsisini kontrol et")
        self.assertEqual((title, steps), ("Yazıcı çıktı vermiyor", ["Kağıt tepsisini kontrol et."]))
        title, steps = learning.basic_structure("iPhone bağlantı sorunu")
        self.assertTrue(title.startswith("İ"))        # Türkçe i -> İ

    def test_nothing_is_invented_or_lost_for_unpunctuated_speech(self):
        title, steps = learning.basic_structure(NO_PUNCT)
        joined = " ".join([title] + steps).lower()
        for word in ("müşteri", "kartına", "numarasını", "hane", "faturayı", "tekrar"):
            self.assertIn(word, joined)                # bilgi kaybolmadı (biçim zayıf olsa da)


class CodesAndTitles(unittest.TestCase):
    def test_verb_plus_number_is_not_an_error_code(self):
        # Canlı testte yaşanan hata: "kontrol et 10 veya 11" -> "ET-10" kodu uydurulmuştu
        self.assertEqual(learning._codes(NO_PUNCT), set())
        title, _ = learning.basic_structure(NO_PUNCT)
        self.assertNotIn("ET-10", title)
        self.assertNotIn("VEYA", title)

    def test_what_counts_as_an_error_code(self):
        for text in ("KNK-204 hatası", "KNK 204 hatası", "KNK204 hatası", "knk-204 hatası", "KNK - 204"):
            self.assertEqual(learning._codes(text), {"KNK-204"}, text)
        for text in ("knk 204 hatası", "kontrol et 10", "veya 11", "windows 10", "port 8080"):
            self.assertEqual(learning._codes(text), set(), text)

    def test_normalize_title(self):
        n = learning.normalize_title
        self.assertEqual(n("Yazıcı KNK-500 Hatası"), "KNK-500: Yazıcı")
        self.assertEqual(n("KNK-500 yazıcı bağlanmıyor"), "KNK-500: Yazıcı bağlanmıyor")
        self.assertEqual(n("knk-500 hatası yazıcı"), "KNK-500: Yazıcı")
        self.assertEqual(n("KNK-500: Yazıcı bağlanmıyor"), "KNK-500: Yazıcı bağlanmıyor")
        self.assertEqual(n("KNK-500 - Yazıcı"), "KNK-500 - Yazıcı")
        self.assertEqual(n("mali mühür görünmüyor"), "Mali mühür görünmüyor")
        self.assertEqual(n("iPhone sorunu"), "İPhone sorunu")

    def test_format_solution(self):
        self.assertEqual(learning.format_solution(["a", "b"]), "Çözüm adımları:\n1. a\n2. b")


if __name__ == "__main__":
    unittest.main()
