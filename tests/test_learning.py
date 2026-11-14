"""Sohbetten öğrenme: komut tanıma, düzenleme/doğrulama, onay akışı ve yetki.
Model sahte, ChromaDB gerçek (geçici klasör), embedding sahte."""
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import intent, knowledge, learning
from app.services import users as u
from tests.test_knowledge import Base, H

INFO = ("KNK-500 yazıcı bağlanmıyor. Önce kabloyu kontrol et sonra servisi yeniden başlat "
        "en son bilgisayarı kapatıp aç")
# Model çıktısı: metin AYNEN tekrarlanmış, yalnızca bölme işaretleri (|) eklenmiş
GOOD_AI = ("KNK-500 yazıcı bağlanmıyor | önce kabloyu kontrol et | sonra servisi yeniden başlat | "
           "en son bilgisayarı kapatıp aç")


def events(resp):
    return [json.loads(b[6:]) for b in resp.text.split("\n\n") if b.startswith("data: ")]


def text_of(ev):
    return "".join(e.get("text", "") for e in ev if e["type"] == "token")


class CommandParsing(unittest.TestCase):
    def test_commands_are_detected_and_content_extracted(self):
        cases = {
            "KNK-500 yazıcı bağlanmıyor. Önce kabloyu kontrol et. Bunu kaydet.":
                "KNK-500 yazıcı bağlanmıyor. Önce kabloyu kontrol et. .",
            "Bunu hafızaya kaydet: KNK-500 yazıcı sorunu kabloyu kontrol et": "KNK-500 yazıcı sorunu kabloyu kontrol et",
            "kaydet: KNK-500 yazıcı sorunu kabloyu kontrol et": "KNK-500 yazıcı sorunu kabloyu kontrol et",
            "Öğren: KNK-500 yazıcı sorunu": "KNK-500 yazıcı sorunu",
            "KNK-500 yazıcı sorunu kabloyu kontrol et, bilgi bankasına ekle": "KNK-500 yazıcı sorunu kabloyu kontrol et,",
            "kaydet": "", "Bunu kaydet": "", "bunu öğren": "", "Kaydet.": "",
        }
        for text, content in cases.items():
            got = intent.parse_learn_command(text)
            self.assertIsNotNone(got, text)
            self.assertEqual(got.strip(" .,"), content.strip(" .,"), text)

    def test_ordinary_sentences_are_not_commands(self):
        for text in ("Kaydet düğmesine basınca hata alıyorum", "ayarları kaydet butonu çalışmıyor",
                     "Faturayı kaydedemiyorum", "dosyayı nasıl kaydederim", "KNK-204 nedir",
                     "öğrenmek istiyorum", "programı kaydetmeden kapattım", "merhaba"):
            self.assertIsNone(intent.parse_learn_command(text), text)

    def test_title_override_parsing(self):
        self.assertEqual(intent.parse_title_override("başlık: KNK-500 Yazıcı"), "KNK-500 Yazıcı")
        self.assertEqual(intent.parse_title_override("Başlığı: Yeni  başlık."), "Yeni başlık")
        self.assertEqual(intent.parse_title_override("BAŞLIK - Deneme"), "Deneme")
        for text in ("başlık", "başlık nedir", "bu kaydın başlığı: x", "KNK-204 nedir", "başlık:"):
            self.assertIsNone(intent.parse_title_override(text), text)

    def test_confirm_and_cancel_words(self):
        for w in ("evet", "Evet.", "kaydet", "Kaydet!", "onayla", "evet kaydet"):
            self.assertTrue(intent.is_confirm(w), w)
        for w in ("iptal", "İptal", "hayır", "vazgeç", "kaydetme"):
            self.assertTrue(intent.is_cancel(w), w)
        for w in ("tamam", "belki", "evet ama başlığı değiştir", "KNK-204 nedir"):
            self.assertFalse(intent.is_confirm(w) or intent.is_cancel(w), w)


class LearnFlow(Base):
    def setUp(self):
        super().setUp()
        u._fails.clear()
        self.stack = []
        self.ai = patch("app.services.llm.complete_text", side_effect=ConnectionError("model yok"))  # basic yol
        self.ai_mock = self.ai.start()
        self.admin = self._client()
        self.admin.post("/api/auth/setup", json={"username": "ayse", "password": "sifre123"})
        self.admin.post("/api/admin/users", json={"username": "bob", "password": "sifre123"})
        self.bob = self._client()
        self.bob.post("/api/auth/login", json={"username": "bob", "password": "sifre123"})

    def _client(self):
        c = TestClient(app, base_url="https://testserver", headers=H)
        c.__enter__()
        self.stack.append(c)
        return c

    def tearDown(self):
        self.ai.stop()
        for c in self.stack:
            c.__exit__(None, None, None)
        super().tearDown()

    def conv(self, client):
        return client.post("/api/chat/conversations").json()["id"]

    def say(self, client, cid, text):
        return events(client.post(f"/api/chat/conversations/{cid}/stream", json={"message": text}))

    # --- admin: anlat + kaydet -> önizleme -> onay ---
    def test_admin_teaches_previews_then_confirms(self):
        cid = self.conv(self.admin)
        ev = self.say(self.admin, cid, INFO + ". Bunu kaydet.")
        cards = next(e for e in ev if e["type"] == "cards")["cards"]
        self.assertEqual(cards[0]["kind"], "draft")
        self.assertEqual(cards[0]["title"], "KNK-500: Yazıcı bağlanmıyor")
        self.assertIn("1. Kabloyu kontrol et.", cards[0]["solution"])
        self.assertEqual(text_of(ev), settings.learn_preview_basic_message)
        self.assertEqual(knowledge.list_all(), [])                      # onaysız hiçbir şey kaydedilmez
        ev = self.say(self.admin, cid, "kaydet")
        self.assertEqual(next(e for e in ev if e["type"] == "cards")["cards"][0]["kind"], "saved")
        self.assertIn("Kaydedildi", text_of(ev))
        rec = knowledge.list_all()[0]
        self.assertEqual((rec["title"], rec["author"]), ("KNK-500: Yazıcı bağlanmıyor", "ayse"))
        # kaydedilen bilgi hemen sohbette bulunur
        ev = self.say(self.admin, self.conv(self.admin), "knk 500 hatası alıyorum")
        self.assertEqual(ev[0]["type"], "cards")
        self.assertEqual(ev[0]["cards"][0]["title"], "KNK-500: Yazıcı bağlanmıyor")

    def test_cancel_discards_draft(self):
        cid = self.conv(self.admin)
        self.say(self.admin, cid, INFO + ". Bunu kaydet.")
        ev = self.say(self.admin, cid, "iptal")
        self.assertIn("kaydetmedim", text_of(ev))
        self.assertEqual(knowledge.list_all(), [])
        self.assertIsNone(learning.get_draft(1, cid))
        self.say(self.admin, cid, "evet")                                # artık onaylanacak taslak yok
        self.assertEqual(knowledge.list_all(), [])

    def test_bare_save_uses_previous_info_message(self):
        cid = self.conv(self.admin)
        self.say(self.admin, cid, INFO)                                  # sadece anlattı, komut yok
        self.assertEqual(knowledge.list_all(), [])
        ev = self.say(self.admin, cid, "bunu kaydet")
        self.assertEqual(next(e for e in ev if e["type"] == "cards")["cards"][0]["title"],
                         "KNK-500: Yazıcı bağlanmıyor")

    def test_bare_save_without_info_asks_what_to_save(self):
        ev = self.say(self.admin, self.conv(self.admin), "kaydet")
        self.assertEqual(text_of(ev), settings.learn_need_info_message)
        self.assertEqual(knowledge.list_all(), [])

    def test_draft_is_per_conversation(self):
        a = self.conv(self.admin)
        self.say(self.admin, a, INFO + ". Bunu kaydet.")
        ev = self.say(self.admin, self.conv(self.admin), "kaydet")       # başka sohbette onay sayılmaz
        self.assertEqual(text_of(ev), settings.learn_need_info_message)
        self.assertEqual(knowledge.list_all(), [])

    def test_duplicate_title_is_reported_without_draft(self):
        knowledge.add("KNK-500: Yazıcı bağlanmıyor", "var olan çözüm", "ayse")
        cid = self.conv(self.admin)
        ev = self.say(self.admin, cid, INFO + ". Bunu kaydet.")
        self.assertIn("zaten var", text_of(ev))
        self.assertIsNone(learning.get_draft(1, cid))
        self.assertEqual(len(knowledge.list_all()), 1)

    def test_confirm_disabled_saves_directly(self):
        with patch.object(settings, "learn_confirm", False):
            ev = self.say(self.admin, self.conv(self.admin), INFO + ". Bunu kaydet.")
        self.assertIn("Kaydedildi", text_of(ev))
        self.assertEqual(len(knowledge.list_all()), 1)

    def test_ai_structured_draft_is_used_when_valid(self):
        with patch("app.services.llm.complete_text", return_value=GOOD_AI):
            ev = self.say(self.admin, self.conv(self.admin), INFO + ". Bunu kaydet.")
        card = next(e for e in ev if e["type"] == "cards")["cards"][0]
        self.assertEqual(card["title"], "KNK-500: Yazıcı bağlanmıyor")
        self.assertIn("1. Kabloyu kontrol et.", card["solution"])
        self.assertEqual(text_of(ev), settings.learn_preview_message)   # "yapay zeka düzenledi, kontrol edin"
        self.assertIn("yapay zeka", settings.learn_preview_message)

    # --- başlık düzeltme ("başlık: ...") ---
    def test_admin_can_fix_title_before_saving(self):
        cid = self.conv(self.admin)
        self.say(self.admin, cid, INFO + ". Bunu kaydet.")
        ev = self.say(self.admin, cid, "başlık: KNK-500: Yazıcı kablo sorunu")
        card = next(e for e in ev if e["type"] == "cards")["cards"][0]
        self.assertEqual((card["kind"], card["title"]), ("draft", "KNK-500: Yazıcı kablo sorunu"))
        self.assertIn("Kabloyu kontrol et.", card["solution"])           # adımlar aynı kaldı
        self.assertEqual(knowledge.list_all(), [])                       # hâlâ kaydedilmedi
        self.say(self.admin, cid, "kaydet")
        self.assertEqual(knowledge.list_all()[0]["title"], "KNK-500: Yazıcı kablo sorunu")

    def test_title_override_rules(self):
        knowledge.add("Var olan başlık", "çözüm", "ayse")
        cid = self.conv(self.admin)
        # taslak yokken "başlık:" sıradan bir mesajdır
        ev = self.say(self.admin, cid, "başlık: bir şey")
        draft_cards = [c for e in ev if e["type"] == "cards" for c in e["cards"] if c.get("kind")]
        self.assertEqual(draft_cards, [])                      # taslak/kaydedildi kartı çıkmaz
        self.assertIsNone(learning.get_draft(1, cid))
        self.say(self.admin, cid, INFO + ". Bunu kaydet.")
        self.assertIn("zaten var", text_of(self.say(self.admin, cid, "başlık: var olan BAŞLIK")))
        self.assertIn("en fazla", text_of(self.say(self.admin, cid, "başlık: " + "x" * 300)))
        self.assertEqual(learning.get_draft(1, cid)["title"], "KNK-500: Yazıcı bağlanmıyor")  # değişmedi

    def test_standard_user_cannot_override_titles_or_confirm(self):
        cid = self.conv(self.bob)
        self.say(self.bob, cid, "başlık: Deneme başlığı")
        self.say(self.bob, cid, "evet")
        self.assertEqual(knowledge.list_all(), [])
        self.assertIsNone(learning.get_draft(2, cid))

    # --- personel: kaydedemez ---
    def test_standard_user_cannot_save_anything(self):
        cid = self.conv(self.bob)
        for msg in (INFO + ". Bunu kaydet.", "kaydet", "kaydet: " + INFO, "bunu hafızaya kaydet"):
            ev = self.say(self.bob, cid, msg)
            self.assertEqual(text_of(ev), settings.learn_denied_message, msg)
            self.assertFalse(any(e["type"] == "cards" for e in ev), msg)
        self.assertEqual(knowledge.list_all(), [])
        self.ai_mock.assert_not_called()                                  # model bile çağrılmadı
        self.assertIsNone(learning.get_draft(2, cid))

    def test_ordinary_question_with_word_save_is_not_blocked(self):
        ev = self.say(self.bob, self.conv(self.bob), "Kaydet düğmesine basınca hata alıyorum")
        self.assertNotEqual(text_of(ev), settings.learn_denied_message)

    def test_demoted_admin_cannot_confirm_old_draft(self):
        self.admin.patch("/api/admin/users/2/role", json={"role": "admin"})   # bob admin oldu
        cid = self.conv(self.bob)
        self.say(self.bob, cid, INFO + ". Bunu kaydet.")
        self.assertIsNotNone(learning.get_draft(2, cid))
        self.admin.patch("/api/admin/users/2/role", json={"role": "user"})    # yetkisi alındı
        ev = self.say(self.bob, cid, "kaydet")
        self.assertEqual(text_of(ev), settings.learn_denied_message)
        self.assertEqual(knowledge.list_all(), [])

    def test_ollama_down_at_confirm_keeps_draft(self):
        cid = self.conv(self.admin)
        self.say(self.admin, cid, INFO + ". Bunu kaydet.")
        with patch("app.services.knowledge.embed", side_effect=ConnectionError("down")):
            ev = self.say(self.admin, cid, "kaydet")
        self.assertIn("Ollama", text_of(ev))
        self.assertIsNotNone(learning.get_draft(1, cid))
        self.assertEqual(knowledge.list_all(), [])
        ev = self.say(self.admin, cid, "kaydet")                           # Ollama gelince tekrar dene
        self.assertIn("Kaydedildi", text_of(ev))


if __name__ == "__main__":
    unittest.main()
