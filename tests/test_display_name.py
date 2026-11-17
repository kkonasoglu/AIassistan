"""Görünen ad (hitap): Dinyo kullanıcıya gerçek adıyla seslenir."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.database import init_db
from app.main import app
from app.services import intent
from app.services import users as u
from tests.test_chat import events, text_of

H = {"X-Requested-With": "fetch"}


class DisplayName(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        settings.data_dir = Path(self._tmp.name)
        u._fails.clear()
        self.stack = []
        self.admin = self.client()
        self.admin.post("/api/auth/setup", json={"username": "konasoglu", "password": "sifre123",
                                                  "display_name": "  kerem   Konasoğlu "})

    def client(self):
        c = TestClient(app, base_url="https://testserver", headers=H)
        c.__enter__(); self.stack.append(c)
        return c

    def tearDown(self):
        for c in self.stack:
            c.__exit__(None, None, None)
        self._tmp.cleanup()

    def test_setup_stores_cleaned_name_and_me_returns_call_name(self):
        me = self.admin.get("/api/auth/me").json()
        self.assertEqual(me["display_name"], "kerem Konasoğlu")      # boşluklar düzeltildi
        self.assertEqual(me["call_name"], "Kerem")                    # ilk sözcük, baş harf büyük

    def test_call_name_falls_back_to_username(self):
        self.admin.post("/api/admin/users", json={"username": "ayse", "password": "sifre123"})
        ayse = self.client()
        me = ayse.post("/api/auth/login", json={"username": "ayse", "password": "sifre123"}).json()
        self.assertEqual((me["display_name"], me["call_name"]), ("", "Ayse"))

    def test_turkish_capitalisation(self):
        self.assertEqual(u.User(1, "x", "user", True, "ismail demir").call_name, "İsmail")
        self.assertEqual(u.User(1, "ığdır", "user", True).call_name, "Iğdır")

    def test_user_can_set_own_name_and_it_persists(self):
        self.admin.post("/api/admin/users", json={"username": "ayse", "password": "sifre123"})
        ayse = self.client()
        ayse.post("/api/auth/login", json={"username": "ayse", "password": "sifre123"})
        r = ayse.post("/api/auth/display-name", json={"name": "Ayşe Yılmaz"})
        self.assertEqual(r.json()["call_name"], "Ayşe")
        self.assertEqual(ayse.get("/api/auth/me").json()["display_name"], "Ayşe Yılmaz")

    def test_admin_can_set_anyones_name_but_user_cannot(self):
        self.admin.post("/api/admin/users", json={"username": "ayse", "password": "sifre123",
                                                   "display_name": "Ayşe"})
        rows = {x["username"]: x for x in self.admin.get("/api/admin/users").json()}
        self.assertEqual(rows["ayse"]["display_name"], "Ayşe")
        self.assertEqual(self.admin.patch(f"/api/admin/users/{rows['ayse']['id']}/display-name",
                                          json={"name": "Ayşe H."}).status_code, 200)
        ayse = self.client()
        ayse.post("/api/auth/login", json={"username": "ayse", "password": "sifre123"})
        r = ayse.patch(f"/api/admin/users/{rows['konasoglu']['id']}/display-name", json={"name": "Hacker"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.admin.get("/api/auth/me").json()["display_name"], "kerem Konasoğlu")

    def test_too_long_name_rejected(self):
        r = self.admin.post("/api/auth/display-name", json={"name": "a" * 41})
        self.assertEqual(r.status_code, 400)

    def test_greeting_uses_the_real_name_in_chat(self):
        cid = self.admin.post("/api/chat/conversations").json()["id"]
        r = self.admin.post(f"/api/chat/conversations/{cid}/stream", json={"message": "merhaba"})
        self.assertTrue(text_of(events(r)).startswith("Merhaba Kerem!"))

    def test_old_database_gets_the_column(self):
        path = Path(self._tmp.name) / "old"
        path.mkdir()
        settings.data_dir = path
        con = sqlite3.connect(path / "app.db")
        con.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE COLLATE NOCASE,"
                    " password_hash TEXT NOT NULL, role TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1,"
                    " created_at TEXT NOT NULL DEFAULT (datetime('now')))")
        con.execute("INSERT INTO users (username, password_hash, role) VALUES ('eski', 'x', 'admin')")
        con.commit(); con.close()
        init_db()
        con = sqlite3.connect(path / "app.db")
        self.assertEqual(con.execute("SELECT display_name FROM users").fetchone()[0], "")
        con.close()


if __name__ == "__main__":
    unittest.main()
