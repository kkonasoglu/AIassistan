"""Kart üstündeki not: şablon ve model çıktısı doğrulama."""
import unittest

from app.services import notes

HIT = {"title": "KNK-204: Şifre hatalı", "text": "KNK-204: Şifre hatalı\n\n1. Ayarlara gir\n2. Kaydet"}
OTHER = {"title": "KNK-101: Bağlantı", "text": "KNK-101: Bağlantı\n\n1. IP bak"}


class Template(unittest.TestCase):
    def test_single_and_multiple(self):
        self.assertIn('"KNK-204: Şifre hatalı"', notes.template_note([HIT]))
        self.assertIn("2 kayıt", notes.template_note([HIT, OTHER]))


class CleanLlmNote(unittest.TestCase):
    def test_accepts_good_notes(self):
        good = "Şifre sorunu gibi duruyor. Alttaki adımları sırayla deneyin."
        self.assertEqual(notes.clean_llm_note(good, [HIT]), good)
        # soruda geçen kayıt kodunu anmak serbest
        self.assertIsNotNone(notes.clean_llm_note("KNK-204 kaydı bu soruna uyuyor.", [HIT]))

    def test_rejects_invented_error_code(self):
        # Canlı testte görülen gerçek hata: kayıtta olmayan KNK-205
        self.assertIsNone(notes.clean_llm_note("KNK-205: Fatura gönderilmedi.", [HIT]))
        self.assertIsNone(notes.clean_llm_note("Bu KNK-101 hatası.", [HIT]))      # başka kayıt kodu
        self.assertIsNotNone(notes.clean_llm_note("Bu KNK-101 hatası.", [HIT, OTHER]))

    def test_rejects_repeated_steps_and_cjk_and_empty_and_long(self):
        self.assertIsNone(notes.clean_llm_note("Deneyin:\n1. Ayarlara gir", [HIT]))
        self.assertIsNone(notes.clean_llm_note("请按照步骤操作。", [HIT]))
        self.assertIsNone(notes.clean_llm_note("   ", [HIT]))
        self.assertIsNone(notes.clean_llm_note("Cümle. " * 60, [HIT]))

    def test_truncated_note_is_cut_to_last_full_sentence(self):
        # Canlı testte görülen: "... 10 veya 11 hanel" gibi yarıda kesilen çıktılar
        self.assertEqual(notes.clean_llm_note("Anladım. Şimdi adımlara bakın ve kul", [HIT]),
                         "Anladım. Şimdi adımlara bakın ve kul"[:len("Anladım.")])
        self.assertIsNone(notes.clean_llm_note("Hiç cümle bitmeden kesildi", [HIT]))


if __name__ == "__main__":
    unittest.main()
