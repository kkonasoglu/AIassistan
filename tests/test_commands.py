"""Emir/komut anlama: "merhaba de" dendiğinde Dinyo "Merhaba!" der, "yapamam/bulamadım" demez."""
import datetime
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import commands as c
from app.services import users as u
from tests.test_chat import HIT, events, text_of

H = {"X-Requested-With": "fetch"}
NO_LAST = lambda: None


def quick(t, last=NO_LAST):
    return c.quick_reply(t, "Kerem", last)


class Parsing(unittest.TestCase):
    def test_say_commands(self):
        self.assertEqual(c.weak_say("merhaba de"), "Merhaba!")
        self.assertEqual(c.weak_say("Bana günaydın de"), "Günaydın!")
        self.assertEqual(c.weak_say("kolay gelsin yaz"), "Kolay gelsin!")
        self.assertEqual(quick("selam söyle"), "Selam!")
        self.assertEqual(quick("de ki kolay gelsin"), "Kolay gelsin!")
        self.assertEqual(quick("şunu söyle: yarın görüşürüz"), "Yarın görüşürüz!")
        self.assertEqual(quick('"Merhaba dünya" diye söyle'), "Merhaba dünya!")
        self.assertEqual(quick("İyi akşamlar söyler misin?"), "İyi akşamlar!")

    def test_followups_are_not_commands(self):
        for t in ("3. adımı tekrar yaz", "2. adımı söyle", "bunu tekrar yaz"):
            self.assertIsNone(c.weak_say(t), t)
        self.assertNotIn("Adım", quick("2. adımı söyle") or "")

    def test_support_questions_are_not_commands(self):
        for t in ("KNK-204 hatası alıyorum", "e-fatura hatası nasıl çözülür", "yazıcı çalışmıyor ve internet de",
                  "teşekkürler", "merhaba"):
            self.assertIsNone(quick(t), t)
            self.assertIsNone(c.weak_say(t), t)

    def test_long_or_empty_content_is_ignored(self):
        self.assertIsNone(c.weak_say("de"))
        self.assertIsNone(c.weak_say("bir iki üç dört beş altı yedi de"))
        self.assertIsNone(quick("😀 söyle"))

    def test_identity_help_and_name(self):
        self.assertIn("Dinyo", quick("sen kimsin"))
        self.assertIn("Dinyo", quick("adın ne"))
        self.assertIn("Kerem", quick("adımı söyle"))          # "söyle" komutu değil, ad sorusu
        self.assertIn("Kerem", quick("benim adım ne"))
        self.assertIn("hata kodunu", quick("ne yapabilirsin"))
        self.assertIn("Tabii Kerem", quick("bana yardım eder misin"))

    def test_time_and_date(self):
        fixed = datetime.datetime(2026, 11, 17, 15, 42)
        with patch.object(c, "_now", return_value=fixed):
            self.assertEqual(quick("saat kaç"), "Saat 15:42.")
            self.assertEqual(quick("Bugün günlerden ne?"), "Bugün 17 Kasım 2026, Salı.")

    def test_repeat(self):
        self.assertEqual(quick("tekrar et", lambda: "Önceki cevap"), "Önceki cevap")
        self.assertEqual(quick("bir daha söyle", lambda: "Önceki cevap"), "Önceki cevap")
        self.assertIn("tekrar edecek", quick("tekrar"))


class ChatFlow(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        settings.data_dir = Path(self._tmp.name)
        u._fails.clear()
        self.cl = TestClient(app, base_url="https://testserver", headers=H)
        self.cl.__enter__()
        self.cl.post("/api/auth/setup", json={"username": "kerem", "password": "sifre123", "display_name": "Kerem"})
        self.cid = self.cl.post("/api/chat/conversations").json()["id"]

    def tearDown(self):
        self.cl.__exit__(None, None, None)
        self._tmp.cleanup()

    def ask(self, msg):
        return events(self.cl.post(f"/api/chat/conversations/{self.cid}/stream", json={"message": msg}))

    def test_merhaba_de_is_done_not_refused(self):
        with patch.object(settings, "web_search", True), patch("app.services.rag.search", return_value=[]), \
             patch("app.services.rag.count", return_value=3), patch("app.services.llm.chat_stream") as cs, \
             patch("app.services.websearch.search") as ws:
            ev = self.ask("merhaba de")
        self.assertEqual(text_of(ev), "Merhaba!")
        for bad in ("bulamadım", "yapamam", "internette aramamı"):
            self.assertNotIn(bad, text_of(ev))
        cs.assert_not_called(); ws.assert_not_called()
        self.assertEqual(ev[-1]["type"], "done")

    def test_strong_command_skips_the_knowledge_base(self):
        with patch("app.services.rag.search") as search:
            ev = self.ask("sen kimsin")
        search.assert_not_called()
        self.assertIn("Dinyo", text_of(ev))

    def test_knowledge_base_wins_over_ambiguous_form(self):
        with patch("app.services.rag.search", return_value=[HIT]):
            ev = self.ask("KNK-204 de")
        self.assertTrue([e for e in ev if e["type"] == "cards"])
        self.assertNotIn("Knk", text_of(ev))

    def test_repeat_repeats_the_last_reply_with_cards(self):
        with patch("app.services.rag.search", return_value=[HIT]):
            self.ask("KNK-204")
        with patch("app.services.rag.search", return_value=[]) as search:
            ev = self.ask("tekrar et")
        search.assert_not_called()
        self.assertIn(HIT["title"], text_of(ev))
        self.assertIn("Ayarlara gir", text_of(ev))

    def test_followup_still_works(self):
        with patch("app.services.rag.search", return_value=[HIT]):
            self.ask("KNK-204")
        with patch("app.services.rag.search", return_value=[]), patch("app.services.rag.count", return_value=3):
            ev = self.ask("2. adımı tekrar yaz")
        self.assertIn("Şifreyi karşılaştır", text_of(ev))


if __name__ == "__main__":
    unittest.main()
