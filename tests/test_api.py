"""Web API testleri (giriş, oturum, roller, admin kuralları).
Çalıştırma:  .venv\\Scripts\\python.exe -m unittest discover tests
"""
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import users as u

H = {"X-Requested-With": "fetch"}


def new_client() -> TestClient:
    # https adresi: çerez "Secure" olduğu için gerekli
    return TestClient(app, base_url="https://testserver", headers=H)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        settings.data_dir = Path(self._tmp.name)
        u._fails.clear()
        self._ctx = new_client()
        self.admin = self._ctx.__enter__()  # lifespan -> init_db

    def tearDown(self):
        self._ctx.__exit__(None, None, None)
        self._tmp.cleanup()

    def setup_admin(self):
        r = self.admin.post("/api/auth/setup", json={"username": "ayse", "password": "sifre123"})
        self.assertEqual(r.status_code, 200)
        return r

    def add_user(self, name="bob", role="user") -> int:
        r = self.admin.post("/api/admin/users", json={"username": name, "password": "sifre123", "role": role})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["id"]

    def login(self, name="bob") -> TestClient:
        c = new_client()
        c.__enter__()
        self.addCleanup(c.__exit__, None, None, None)
        r = c.post("/api/auth/login", json={"username": name, "password": "sifre123"})
        self.assertEqual(r.status_code, 200, r.text)
        return c

    # --- kurulum ve giriş ---
    def test_setup_flow(self):
        self.assertTrue(self.admin.get("/api/auth/state").json()["setup_needed"])
        self.setup_admin()
        st = self.admin.get("/api/auth/state").json()
        self.assertFalse(st["setup_needed"])
        self.assertEqual(st["user"]["role"], "admin")
        # ikinci kurulum denemesi reddedilir
        other = new_client()
        with other:
            r = other.post("/api/auth/setup", json={"username": "x", "password": "sifre123"})
            self.assertEqual(r.status_code, 403)

    def test_cookie_flags_and_no_plain_token_in_db(self):
        r = self.setup_admin()
        cookie = r.headers["set-cookie"].lower()
        for flag in ("httponly", "secure", "samesite=strict"):
            self.assertIn(flag, cookie)
        token = self.admin.cookies.get("ofis_session")
        import sqlite3
        db = sqlite3.connect(settings.db_path)
        rows = db.execute("SELECT token_hash FROM sessions").fetchall()
        db.close()
        self.assertTrue(rows and all(token != r[0] for r in rows))

    def test_requires_login_and_csrf_header(self):
        self.setup_admin()
        anon = new_client()
        with anon:
            self.assertEqual(anon.get("/api/auth/me").status_code, 401)
            self.assertEqual(anon.get("/api/admin/users").status_code, 401)
        nohdr = TestClient(app, base_url="https://testserver")
        with nohdr:
            r = nohdr.post("/api/auth/login", json={"username": "ayse", "password": "sifre123"})
            self.assertEqual(r.status_code, 403)

    def test_logout_invalidates_session(self):
        self.setup_admin()
        self.assertEqual(self.admin.get("/api/auth/me").status_code, 200)
        token = self.admin.cookies.get("ofis_session")
        self.admin.post("/api/auth/logout")
        self.admin.cookies.set("ofis_session", token)  # eski jetonla tekrar dene
        self.assertEqual(self.admin.get("/api/auth/me").status_code, 401)

    # --- roller ---
    def test_user_cannot_use_admin_api(self):
        self.setup_admin(); self.add_user()
        bob = self.login()
        self.assertEqual(bob.get("/api/admin/users").status_code, 403)
        self.assertEqual(bob.post("/api/admin/users", json={"username": "z", "password": "sifre123"}).status_code, 403)
        self.assertEqual(bob.post("/api/admin/transfer", json={"target_id": 1}).status_code, 403)

    def test_last_admin_rule_over_http(self):
        self.setup_admin()
        me = self.admin.get("/api/auth/me").json()["id"]
        self.assertEqual(self.admin.patch(f"/api/admin/users/{me}/role", json={"role": "user"}).status_code, 409)
        self.assertEqual(self.admin.patch(f"/api/admin/users/{me}/active", json={"active": False}).status_code, 409)

    def test_role_change_is_immediate(self):
        self.setup_admin(); bob_id = self.add_user()
        bob = self.login()
        self.assertEqual(bob.get("/api/admin/users").status_code, 403)
        self.admin.patch(f"/api/admin/users/{bob_id}/role", json={"role": "admin"})
        self.assertEqual(bob.get("/api/admin/users").status_code, 200)  # yeniden giriş gerekmeden
        self.admin.patch(f"/api/admin/users/{bob_id}/role", json={"role": "user"})
        self.assertEqual(bob.get("/api/admin/users").status_code, 403)

    def test_deactivate_kills_session(self):
        self.setup_admin(); bob_id = self.add_user()
        bob = self.login()
        self.assertEqual(bob.get("/api/auth/me").status_code, 200)
        self.admin.patch(f"/api/admin/users/{bob_id}/active", json={"active": False})
        self.assertEqual(bob.get("/api/auth/me").status_code, 401)
        c = new_client()
        with c:
            self.assertEqual(c.post("/api/auth/login", json={"username": "bob", "password": "sifre123"}).status_code, 401)

    def test_transfer_admin(self):
        self.setup_admin(); bob_id = self.add_user()
        bob = self.login()
        self.assertEqual(self.admin.post("/api/admin/transfer", json={"target_id": bob_id}).status_code, 200)
        self.assertEqual(self.admin.get("/api/admin/users").status_code, 403)   # ayse artık user
        self.assertEqual(bob.get("/api/admin/users").status_code, 200)          # bob artık admin

    def test_password_change(self):
        self.setup_admin(); self.add_user()
        bob = self.login()
        self.assertEqual(bob.post("/api/auth/password", json={"current": "yanlis", "new": "yeniSifre1"}).status_code, 401)
        self.assertEqual(bob.post("/api/auth/password", json={"current": "sifre123", "new": "123"}).status_code, 400)
        self.assertEqual(bob.post("/api/auth/password", json={"current": "sifre123", "new": "yeniSifre1"}).status_code, 200)
        self.assertEqual(bob.get("/api/auth/me").status_code, 200)  # kendi oturumu açık kalır
        c = new_client()
        with c:
            self.assertEqual(c.post("/api/auth/login", json={"username": "bob", "password": "yeniSifre1"}).status_code, 200)

    def test_user_list_has_no_password_hash(self):
        self.setup_admin(); self.add_user()
        text = self.admin.get("/api/admin/users").text
        self.assertNotIn("hash", text.lower())
        self.assertNotIn("argon2", text.lower())


if __name__ == "__main__":
    unittest.main()
