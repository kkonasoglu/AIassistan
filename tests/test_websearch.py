"""İnternet araması: kayıt yoksa otomatik devreye girer, gizlilik temizliği, hata durumları.
Gerçek internete çıkılmaz (arama sahte veriyle değiştirilir)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import users as u
from app.services import websearch
from tests.test_chat import HIT, events, text_of

H = {"X-Requested-With": "fetch"}
WEB = [{"title": "Yazıcı sorunları", "snippet": "Önce kabloyu kontrol edin.", "url": "https://example.com/a"},
       {"title": "Sürücü", "snippet": "Sürücüyü yeniden kurun.", "url": "https://example.com/b"}]


class Sanitize(unittest.TestCase):
    def test_removes_emails_and_long_numbers(self):
        q = websearch.sanitize("ali@firma.com vergi no 1234567890 için e-fatura hatası 204")
        self.assertNotIn("@", q)
        self.assertNotIn("1234567890", q)
        self.assertIn("e-fatura hatası 204", q)

    def test_removes_phone_and_formatted_numbers(self):
        self.assertNotIn("555", websearch.sanitize("beni 0 555 123 45 67 numarasından ara yazıcı"))

    def test_limits_length(self):
        self.assertLessEqual(len(websearch.sanitize("a " * 500)), websearch.MAX_QUERY)


class SearchFunction(unittest.TestCase):
    def test_returns_only_http_results(self):
        raw = [{"title": "A", "href": "https://a.com", "body": "x"},
               {"title": "B", "href": "javascript:alert(1)", "body": "y"},
               {"title": "C", "href": "file:///c:/x", "body": "z"}]
        with patch("ddgs.DDGS") as d:
            d.return_value.text.return_value = raw
            r = websearch.search("yazıcı sorunu")
        self.assertEqual([x["url"] for x in r], ["https://a.com"])

    def test_sends_only_sanitized_query(self):
        with patch("ddgs.DDGS") as d:
            d.return_value.text.return_value = []
            websearch.search("mail ali@firma.com yazıcı çalışmıyor")
        sent = d.return_value.text.call_args.args[0]
        self.assertNotIn("ali@firma.com", sent)

    def test_network_failure_returns_empty(self):
        with patch("ddgs.DDGS", side_effect=OSError("internet yok")):
            self.assertEqual(websearch.search("yazıcı sorunu"), [])

    def test_retries_once_after_a_failure(self):
        ok = [{"title": "A", "href": "https://a.com", "body": "x"}]
        with patch("ddgs.DDGS") as d, patch("time.sleep"):
            d.return_value.text.side_effect = [Exception("No results found"), ok]
            self.assertEqual(len(websearch.search("dolar kaç tl")), 1)
        self.assertEqual(d.return_value.text.call_count, 2)

    def test_too_short_query_is_not_sent(self):
        with patch("ddgs.DDGS") as d:
            self.assertEqual(websearch.search("12345678"), [])
        d.assert_not_called()


class ChatFallback(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        settings.data_dir = Path(self._tmp.name)
        u._fails.clear()
        self.c = TestClient(app, base_url="https://testserver", headers=H)
        self.c.__enter__()
        self.c.post("/api/auth/setup", json={"username": "ayse", "password": "sifre123"})
        self.cid = self.c.post("/api/chat/conversations").json()["id"]

    def tearDown(self):
        self.c.__exit__(None, None, None)
        self._tmp.cleanup()

    def ask(self, msg):
        return events(self.c.post(f"/api/chat/conversations/{self.cid}/stream", json={"message": msg}))

    NO_KB = dict(search=[], count=3)

    def _no_kb(self):
        return patch("app.services.rag.search", return_value=[]), patch("app.services.rag.count", return_value=3)

    def test_no_kb_hit_asks_before_searching(self):
        a, b = self._no_kb()
        with patch.object(settings, "web_search", True), a, b,              patch("app.services.websearch.search") as ws, patch("app.services.llm.chat_stream") as cs:
            ev = self.ask("yazıcı ağda görünmüyor")
        ws.assert_not_called()                                    # onay olmadan internete çıkılmaz
        cs.assert_not_called()
        self.assertEqual(text_of(ev), f"{settings.no_kb_message} {settings.web_offer_question}")
        self.assertFalse([e for e in ev if e["type"] == "cards"])

    def test_yes_searches_original_question_and_shows_web_cards(self):
        a, b = self._no_kb()
        with patch.object(settings, "web_search", True), a, b,              patch("app.services.websearch.search", return_value=WEB) as ws,              patch("app.services.llm.chat_stream") as cs:
            self.ask("yazıcı ağda görünmüyor")
            ev = self.ask("evet")
        cs.assert_not_called()
        ws.assert_called_once_with("yazıcı ağda görünmüyor")      # "evet" değil, asıl soru aranır
        cards = next(e for e in ev if e["type"] == "cards")["cards"]
        self.assertEqual([c["kind"] for c in cards], ["web", "web"])
        self.assertEqual(cards[0]["url"], "https://example.com/a")
        self.assertEqual(text_of(ev), settings.web_note)
        saved = self.c.get(f"/api/chat/conversations/{self.cid}").json()[-1]
        self.assertEqual(saved["cards"][0]["kind"], "web")

    def test_no_declines_without_searching(self):
        a, b = self._no_kb()
        with patch.object(settings, "web_search", True), a, b,              patch("app.services.websearch.search") as ws:
            self.ask("yazıcı ağda görünmüyor")
            ev = self.ask("hayır")
        ws.assert_not_called()
        self.assertEqual(text_of(ev), settings.web_declined_message)

    def test_answer_only_counts_right_after_the_offer(self):
        a, b = self._no_kb()
        with patch.object(settings, "web_search", True), a, b,              patch("app.services.websearch.search") as ws:
            self.ask("yazıcı ağda görünmüyor")
            self.ask("merhaba")                                   # teklif geçti
            ev = self.ask("evet")
        ws.assert_not_called()                                    # eski teklife "evet" denmez

    def test_new_question_after_offer_is_a_new_question(self):
        a, b = self._no_kb()
        with patch.object(settings, "web_search", True), a, b,              patch("app.services.websearch.search") as ws:
            self.ask("yazıcı ağda görünmüyor")
            ev = self.ask("ağ kablosu takılı değil")
        ws.assert_not_called()
        self.assertIn(settings.web_offer_question, text_of(ev))   # yeni soru için yeniden sorar

    def test_yes_with_failed_search_says_so(self):
        a, b = self._no_kb()
        with patch.object(settings, "web_search", True), a, b,              patch("app.services.websearch.search", return_value=[]):
            self.ask("yazıcı ağda görünmüyor")
            ev = self.ask("evet")
        self.assertEqual(text_of(ev), settings.web_failed_note.strip())
        self.assertEqual(ev[-1]["type"], "done")

    def test_empty_kb_also_asks(self):
        with patch.object(settings, "web_search", True),              patch("app.services.rag.search", return_value=[]), patch("app.services.rag.count", return_value=0):
            ev = self.ask("yazıcı ağda görünmüyor")
        self.assertEqual(text_of(ev), f"{settings.empty_kb_message} {settings.web_offer_question}")

    def test_kb_hit_never_asks_or_searches(self):
        with patch.object(settings, "web_search", True),              patch("app.services.rag.search", return_value=[HIT]),              patch("app.services.websearch.search") as ws:
            ev = self.ask("KNK-204")
        ws.assert_not_called()
        self.assertNotIn(settings.web_offer_question, text_of(ev))

    def test_greeting_never_asks(self):
        with patch.object(settings, "web_search", True),              patch("app.services.rag.search", return_value=[]), patch("app.services.websearch.search") as ws:
            ev = self.ask("merhaba")
        ws.assert_not_called()
        self.assertNotIn(settings.web_offer_question, text_of(ev))

    def test_switch_off_neither_asks_nor_searches(self):
        a, b = self._no_kb()
        with patch.object(settings, "web_search", False), a, b,              patch("app.services.websearch.search") as ws:
            ev = self.ask("yazıcı ağda görünmüyor")
            ev2 = self.ask("evet")
        ws.assert_not_called()
        self.assertEqual(text_of(ev), settings.no_kb_message)


if __name__ == "__main__":
    unittest.main()
