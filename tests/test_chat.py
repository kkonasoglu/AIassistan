"""Sohbet testleri: geçmiş, sahiplik, hafıza, kuyruk, akış API'si (kart + not).
Model ve arama sahte veriyle değiştirilir (gerçek Ollama çağrılmaz)."""
import asyncio
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.database import init_db
from app.main import app
from app.services import chat_store, intent, llm_queue, memory, notes
from app.services import users as u

H = {"X-Requested-With": "fetch"}

HIT = {"text": "KNK-204: Şifre hatalı\n\nÇözüm:\n1. Ayarlara gir\n2. Şifreyi karşılaştır\n3. Kaydet",
       "title": "KNK-204: Şifre hatalı",
       "solution": "Çözüm:\n1. Ayarlara gir\n2. Şifreyi karşılaştır\n3. Kaydet", "distance": 0.2}


def events(resp) -> list[dict]:
    out = []
    for block in resp.text.split("\n\n"):
        if block.startswith("data: "):
            out.append(json.loads(block[6:]))
    return out


def text_of(ev) -> str:
    return "".join(e.get("text", "") for e in ev if e["type"] == "token")


class StoreAndMemory(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        settings.data_dir = Path(self._tmp.name)
        init_db()
        self.a = u.create_user("ayse", "sifre123")
        self.b = u.create_user("bob", "sifre123", "user", self.a.id)

    def tearDown(self):
        self._tmp.cleanup()

    def test_ownership(self):
        cid = chat_store.create_conversation(self.a.id)
        chat_store.add_message(self.a.id, cid, "user", "merhaba")
        with self.assertRaises(chat_store.NotFound):
            chat_store.get_messages(self.b.id, cid)
        with self.assertRaises(chat_store.NotFound):
            chat_store.add_message(self.b.id, cid, "user", "x")
        with self.assertRaises(chat_store.NotFound):
            chat_store.delete_conversation(self.b.id, cid)
        self.assertEqual(chat_store.list_conversations(self.b.id), [])

    def test_title_from_first_question_and_delete(self):
        cid = chat_store.create_conversation(self.a.id)
        chat_store.add_message(self.a.id, cid, "user", "KNK-204 hatası\naldım " + "x" * 80)
        title = chat_store.list_conversations(self.a.id)[0]["title"]
        self.assertTrue(title.startswith("KNK-204 hatası aldım") and title.endswith("…"))
        chat_store.add_message(self.a.id, cid, "user", "ikinci soru")
        self.assertEqual(chat_store.list_conversations(self.a.id)[0]["title"], title)
        chat_store.delete_conversation(self.a.id, cid)
        self.assertEqual(chat_store.list_conversations(self.a.id), [])

    def test_cards_roundtrip(self):
        cid = chat_store.create_conversation(self.a.id)
        cards = [{"title": "T", "solution": "1. a\n2. b"}]
        chat_store.add_message(self.a.id, cid, "assistant", "not", ["T"], cards)
        got = chat_store.get_messages(self.a.id, cid)[0]
        self.assertEqual((got["content"], got["cards"], got["sources"]), ("not", cards, ["T"]))

    def test_window_limits_turns_and_starts_with_user(self):
        cid = chat_store.create_conversation(self.a.id)
        for i in range(20):
            chat_store.add_message(self.a.id, cid, "user", f"soru {i}")
            chat_store.add_message(self.a.id, cid, "assistant", f"cevap {i}")
        chat_store.add_message(self.a.id, cid, "user", "son soru")
        w = memory.window(self.a.id, cid)
        self.assertLessEqual(len(w), settings.history_turns * 2 + 1)
        self.assertEqual(w[0]["role"], "user")
        self.assertEqual(w[-1]["content"], "son soru")

    def test_window_char_budget_keeps_last_message(self):
        cid = chat_store.create_conversation(self.a.id)
        chat_store.add_message(self.a.id, cid, "user", "a" * 5000)
        chat_store.add_message(self.a.id, cid, "assistant", "b" * 5000)
        chat_store.add_message(self.a.id, cid, "user", "son")
        self.assertEqual([m["content"] for m in memory.window(self.a.id, cid)], ["son"])

    def test_window_includes_card_text_for_model_and_step_lookup(self):
        cid = chat_store.create_conversation(self.a.id)
        chat_store.add_message(self.a.id, cid, "user", "KNK-204?")
        chat_store.add_message(self.a.id, cid, "assistant", "Kısa not.", ["T"],
                               [{"title": "T", "solution": "1. Ayarlara gir\n2. Kaydet"}])
        chat_store.add_message(self.a.id, cid, "user", "2. adımı tekrar yaz")
        w = memory.window(self.a.id, cid)
        self.assertIn("1. Ayarlara gir", w[1]["content"])
        self.assertIn("Kısa not.", w[1]["content"])
        self.assertEqual(memory.step_from_previous(w[:-1], "2. adımı tekrar yaz"), "2. Kaydet")


class OldDatabaseMigration(unittest.TestCase):
    def test_cards_column_added_to_existing_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings.data_dir = Path(tmp)
            db = sqlite3.connect(Path(tmp) / "app.db")
            db.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, conversation_id INTEGER, "
                       "role TEXT, content TEXT, sources TEXT, created_at TEXT)")
            db.commit(); db.close()
            init_db()
            db = sqlite3.connect(Path(tmp) / "app.db")
            cols = [r[1] for r in db.execute("PRAGMA table_info(messages)")]
            db.close()
            self.assertIn("cards", cols)


class Intent(unittest.TestCase):
    def test_smalltalk(self):
        self.assertEqual(intent.smalltalk("Merhaba"), intent.GREETING)
        self.assertEqual(intent.smalltalk("selam!"), intent.GREETING)
        self.assertEqual(intent.smalltalk("Günaydın"), intent.GREETING)
        self.assertEqual(intent.smalltalk("teşekkürler"), intent.THANKS)
        self.assertEqual(intent.smalltalk("Sağ ol"), intent.THANKS)
        self.assertEqual(intent.smalltalk("nasılsın"), intent.HOW_ARE_YOU)
        self.assertEqual(intent.smalltalk("tamam"), intent.ACK)

    def test_not_smalltalk(self):
        for q in ("merhaba fatura gönderemiyorum ve bir hata alıyorum sürekli", "KNK-204 nedir",
                  "Pizza nasıl yapılır?", "", "   "):
            self.assertIsNone(intent.smalltalk(q), q)


class FollowUpDetection(unittest.TestCase):
    def test_followups(self):
        for q in ("Bu çözümün 3. adımını bana tekrar yazar mısın?", "3. adımı tekrar yaz",
                  "bunu daha basit anlat", "Peki neden?", "İkinci adımı açıklar mısın",
                  "Anlamadım", "Başka bir örnek verir misin?"):
            self.assertTrue(memory.looks_like_followup(q), q)

    def test_not_followups(self):
        for q in ("Pizza nasıl yapılır?", "bugün hava nasıl", "Yazıcı kağıt sıkıştırıyor",
                  "Mysoft kurulumu nasıl yapılır"):
            self.assertFalse(memory.looks_like_followup(q), q)


class StepExtraction(unittest.TestCase):
    ANSWER = "Çözüm:\n1. Ayarlara gir\n2. Şifreyi karşılaştır\n3. Test et\n4. Kaydet"

    def test_requested_step(self):
        cases = {"Bu çözümün 3. adımını bana tekrar yazar mısın?": 3, "3.adımı yaz": 3,
                 "ikinci adımı açıkla": 2, "İlk adım ne?": 1, "5. madde nedir": 5,
                 "bunu açıkla": None, "KNK-204 nedir": None}
        for q, n in cases.items():
            self.assertEqual(memory.requested_step(q), n, q)

    def test_extracts_exact_step_from_previous_answer(self):
        hist = [{"role": "user", "content": "q"}, {"role": "assistant", "content": self.ANSWER}]
        self.assertEqual(memory.step_from_previous(hist, "3. adımı tekrar yaz"), "3. Test et")
        self.assertEqual(memory.step_from_previous(hist, "ikinci adımı açıkla"), "2. Şifreyi karşılaştır")
        self.assertIsNone(memory.step_from_previous(hist, "9. adımı yaz"))
        self.assertIsNone(memory.step_from_previous(hist, "bunu açıkla"))


class Queue(unittest.TestCase):
    def test_second_request_waits_and_gets_position(self):
        async def scenario():
            llm_queue.reset()
            order, release = [], asyncio.Event()

            async def first():
                async with llm_queue.slot():
                    order.append("a-start")
                    await release.wait()
                    order.append("a-end")

            async def second():
                self.assertEqual(llm_queue.position_if_wait(), 1)
                async with llm_queue.slot():
                    order.append("b-start")

            t1 = asyncio.create_task(first())
            await asyncio.sleep(0.05)
            t2 = asyncio.create_task(second())
            await asyncio.sleep(0.05)
            self.assertEqual(order, ["a-start"])
            self.assertEqual(llm_queue.waiting_count(), 1)
            release.set()
            await asyncio.gather(t1, t2)
            self.assertEqual(order, ["a-start", "a-end", "b-start"])
            self.assertEqual(llm_queue.waiting_count(), 0)
            self.assertEqual(llm_queue.position_if_wait(), 0)

        asyncio.run(scenario())


class ChatApi(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        settings.data_dir = Path(self._tmp.name)
        u._fails.clear()
        llm_queue.reset()
        self.stack = []
        # Varsayılan: bilgi bankası dolu (boş banka testi bunu kendisi geçersiz kılar)
        self._count = patch("app.services.rag.count", return_value=5)
        self._count.start()
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
        self._count.stop()
        for c in self.stack:
            c.__exit__(None, None, None)
        self._tmp.cleanup()

    def new_conv(self, client) -> int:
        return client.post("/api/chat/conversations").json()["id"]

    def ask(self, client, cid, text, use_kb=True):
        return client.post(f"/api/chat/conversations/{cid}/stream", json={"message": text, "use_kb": use_kb})

    def answered_conv(self, note="Hemen bakalım."):
        """Bilgi bankası kartlı bir cevabı olan sohbet (devam soruları için)."""
        with patch("app.services.rag.search", return_value=[HIT]), \
             patch("app.services.llm.chat_stream", return_value=iter([note])):
            cid = self.new_conv(self.bob)
            self.ask(self.bob, cid, "KNK-204 ne yapmalıyım?")
        return cid

    def test_requires_login(self):
        anon = self._client(); anon.cookies.clear()
        self.assertEqual(anon.get("/api/chat/conversations").status_code, 401)

    # --- alakalı kayıt: kart önce ve birebir, ardından anında şablon not (model yok) ---
    def test_hit_sends_card_then_instant_template_note_without_model(self):
        with patch("app.services.rag.search", return_value=[HIT]),              patch("app.services.llm.chat_stream") as cs:
            cid = self.new_conv(self.bob)
            ev = events(self.ask(self.bob, cid, "programa giremiyorum şifre hatalı diyor"))
        cs.assert_not_called()     # varsayılan modda model hiç çağrılmaz: bekleme yok
        self.assertEqual([e["type"] for e in ev], ["cards", "token", "done"])
        self.assertEqual(ev[0]["cards"], [{"title": HIT["title"], "solution": HIT["solution"]}])
        self.assertEqual(text_of(ev), notes.template_note([HIT]))
        self.assertIn(HIT["title"], text_of(ev))
        saved = self.bob.get(f"/api/chat/conversations/{cid}").json()
        self.assertEqual([m["role"] for m in saved], ["user", "assistant"])
        self.assertEqual(saved[0]["content"], "programa giremiyorum şifre hatalı diyor")  # ham soru
        self.assertEqual(saved[1]["content"], notes.template_note([HIT]))
        self.assertEqual(saved[1]["cards"][0]["title"], HIT["title"])

    def test_several_hits_make_several_cards(self):
        second = {**HIT, "title": "KNK-101: Bağlantı",
                  "text": "KNK-101: Bağlantı\n\n1. IP bak", "solution": "1. IP bak"}
        with patch("app.services.rag.search", return_value=[HIT, second]):
            cid = self.new_conv(self.bob)
            ev = events(self.ask(self.bob, cid, "fatura gitmedi"))
        self.assertEqual([c["title"] for c in ev[0]["cards"]], [HIT["title"], "KNK-101: Bağlantı"])
        self.assertIn("2 kayıt", text_of(ev))

    def test_llm_mode_accepts_a_valid_model_note(self):
        with patch.object(settings, "note_mode", "llm"),              patch("app.services.rag.search", return_value=[HIT]),              patch("app.services.llm.chat_stream",
                   return_value=iter(["Şifre sorunu gibi duruyor.", " Adımlara bakın."])) as cs:
            cid = self.new_conv(self.bob)
            ev = events(self.ask(self.bob, cid, "programa giremiyorum"))
        self.assertEqual([e["type"] for e in ev], ["cards", "token", "done"])  # not tek parça gelir
        self.assertEqual(text_of(ev), "Şifre sorunu gibi duruyor. Adımlara bakın.")
        msgs, system = cs.call_args.args[0], cs.call_args.args[1]
        self.assertEqual(system, settings.note_prompt)
        self.assertEqual(cs.call_args.kwargs["max_tokens"], settings.note_max_tokens)
        self.assertIn("BULUNAN KAYIT:", msgs[-1]["content"])

    def test_llm_mode_replaces_bad_notes_with_template(self):
        bad_notes = [
            "Önce şunu yapın:\n1. Ayarlara gir\n2. Kaydet",            # adımları tekrarlıyor
            "KNK-205 hatası için aşağıdaki adımlara bakın.",           # uydurma hata kodu
            "Kullanıcı adı ve şifrenizi kontrol edin ve kul",          # cümle yarıda kesik, tam cümle yok
            "您好，请按照步骤操作。",                                    # Çince
        ]
        for bad in bad_notes:
            with patch.object(settings, "note_mode", "llm"),                  patch("app.services.rag.search", return_value=[HIT]),                  patch("app.services.llm.chat_stream", return_value=iter([bad])):
                cid = self.new_conv(self.bob)
                ev = events(self.ask(self.bob, cid, "KNK-204"))
            self.assertEqual(text_of(ev), notes.template_note([HIT]), bad)

    def test_llm_mode_card_is_delivered_even_if_model_fails(self):
        def boom(*a, **k):
            raise ConnectionError("ollama kapalı")
            yield
        with patch.object(settings, "note_mode", "llm"),              patch("app.services.rag.search", return_value=[HIT]),              patch("app.services.llm.chat_stream", side_effect=boom):
            cid = self.new_conv(self.bob)
            ev = events(self.ask(self.bob, cid, "KNK-204"))
        self.assertEqual([e["type"] for e in ev], ["cards", "token", "done"])  # hata yok
        self.assertEqual(text_of(ev), notes.template_note([HIT]))

    # --- eşleşme yok ---
    def test_no_hits_does_not_call_llm(self):
        with patch("app.services.rag.search", return_value=[]), \
             patch("app.services.llm.chat_stream") as cs:
            cid = self.new_conv(self.bob)
            ev = events(self.ask(self.bob, cid, "Pizza nasıl yapılır?"))
        cs.assert_not_called()
        self.assertEqual(text_of(ev), settings.no_kb_message)
        self.assertEqual(ev[-1]["type"], "done")

    def test_empty_knowledge_base_says_so_instead_of_generic_not_found(self):
        # Gerçek yaşanan durum: banka boştu, kullanıcı "çalışmıyor" sandı
        with patch("app.services.rag.count", return_value=0), \
             patch("app.services.rag.search", return_value=[]), \
             patch("app.services.llm.chat_stream") as cs:
            cid = self.new_conv(self.bob)
            ev = events(self.ask(self.bob, cid, "knk 204 hatası alıyorum"))
            greet = events(self.ask(self.bob, cid, "merhaba"))
        cs.assert_not_called()
        self.assertEqual(text_of(ev), settings.empty_kb_message)
        self.assertIn("boş", text_of(ev))
        self.assertEqual(text_of(greet), intent.GREETING)   # selamlaşma yine normal cevaplanır

    def test_greeting_and_thanks_get_friendly_replies_without_model(self):
        with patch("app.services.rag.search", return_value=[]), \
             patch("app.services.llm.chat_stream") as cs:
            cid = self.new_conv(self.bob)
            self.assertEqual(text_of(events(self.ask(self.bob, cid, "Merhaba"))), intent.GREETING)
            self.assertEqual(text_of(events(self.ask(self.bob, cid, "teşekkürler"))), intent.THANKS)
        cs.assert_not_called()

    def test_kb_hit_wins_over_greeting(self):
        with patch("app.services.rag.search", return_value=[HIT]), \
             patch("app.services.llm.chat_stream", return_value=iter(["Tamam."])):
            cid = self.new_conv(self.bob)
            ev = events(self.ask(self.bob, cid, "merhaba şifre hatalı diyor"))
        self.assertEqual(ev[0]["type"], "cards")

    # --- devam soruları ---
    def test_step_followup_is_answered_by_code_from_card(self):
        cid = self.answered_conv()
        with patch("app.services.rag.search", return_value=[]), \
             patch("app.services.llm.chat_stream") as cs:
            ev = events(self.ask(self.bob, cid, "Bu çözümün 3. adımını tekrar yazar mısın?"))
        cs.assert_not_called()
        self.assertEqual(text_of(ev), "3. Kaydet")

    def test_other_followup_uses_history_only(self):
        cid = self.answered_conv()
        with patch("app.services.rag.search", return_value=[]), \
             patch("app.services.llm.chat_stream", return_value=iter(["Daha basit: ayarlara gir."])) as cs:
            self.ask(self.bob, cid, "bunu daha basit anlat")
        msgs, system = cs.call_args.args[0], cs.call_args.args[1]
        self.assertEqual(system, settings.followup_prompt)
        self.assertNotIn("BULUNAN KAYIT", " ".join(m["content"] for m in msgs))
        self.assertIn("1. Ayarlara gir", msgs[1]["content"])        # önceki cevabın kartı görünür
        self.assertTrue(msgs[-1]["content"].endswith(settings.lang_reminder))

    def test_unrelated_question_after_answer_is_not_answered_from_model_knowledge(self):
        cid = self.answered_conv()
        with patch("app.services.rag.search", return_value=[]), \
             patch("app.services.llm.chat_stream") as cs:
            ev = events(self.ask(self.bob, cid, "Pizza nasıl yapılır?"))
        cs.assert_not_called()
        self.assertEqual(text_of(ev), settings.no_kb_message)

    # --- serbest sohbet, hafıza, sahiplik, doğrulama ---
    def test_without_kb_skips_search_and_uses_default_prompt(self):
        with patch("app.services.rag.search") as search, \
             patch("app.services.llm.chat_stream", return_value=iter(["selam"])) as cs:
            cid = self.new_conv(self.bob)
            ev = events(self.ask(self.bob, cid, "merhaba", use_kb=False))
        search.assert_not_called()
        self.assertIsNone(cs.call_args.args[1])
        self.assertEqual([e["type"] for e in ev], ["token", "done"])

    def test_history_is_sent_to_model_on_second_question(self):
        with patch("app.services.llm.chat_stream", return_value=iter(["x"])):
            cid = self.new_conv(self.bob)
            self.ask(self.bob, cid, "ilk soru", use_kb=False)
        with patch("app.services.llm.chat_stream", return_value=iter(["y"])) as cs:
            self.ask(self.bob, cid, "ikinci soru", use_kb=False)
        self.assertEqual([m["content"] for m in cs.call_args.args[0]], ["ilk soru", "x", "ikinci soru"])

    def test_cannot_touch_other_users_conversation(self):
        cid = self.new_conv(self.admin)
        self.assertEqual(self.bob.get(f"/api/chat/conversations/{cid}").status_code, 404)
        self.assertEqual(self.ask(self.bob, cid, "merhaba").status_code, 404)
        self.assertEqual(self.bob.delete(f"/api/chat/conversations/{cid}").status_code, 404)
        self.assertEqual(self.bob.get("/api/chat/conversations").json(), [])
        self.assertEqual(self.admin.get(f"/api/chat/conversations/{cid}").json(), [])

    def test_validation(self):
        cid = self.new_conv(self.bob)
        self.assertEqual(self.ask(self.bob, cid, "   ").status_code, 400)
        self.assertEqual(self.ask(self.bob, cid, "x" * (settings.max_message_chars + 1)).status_code, 400)

    def test_llm_error_without_card_is_reported_and_no_assistant_message_saved(self):
        def boom(*a, **k):
            raise ConnectionError("ollama kapalı")
            yield
        with patch("app.services.llm.chat_stream", side_effect=boom):
            cid = self.new_conv(self.bob)
            ev = events(self.ask(self.bob, cid, "merhaba", use_kb=False))
        self.assertEqual(ev[-1]["type"], "error")
        saved = self.bob.get(f"/api/chat/conversations/{cid}").json()
        self.assertEqual([m["role"] for m in saved], ["user"])

    def test_delete_conversation(self):
        cid = self.new_conv(self.bob)
        self.assertEqual(self.bob.delete(f"/api/chat/conversations/{cid}").status_code, 200)
        self.assertEqual(self.bob.get(f"/api/chat/conversations/{cid}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
