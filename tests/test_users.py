"""Çalıştırma (proje klasöründen):  C:\\venvs\\ofis\\Scripts\\python.exe -m unittest discover tests"""
import tempfile
import unittest
from pathlib import Path

from app.core.config import settings
from app.db.database import init_db
from app.services import users as u


class UserRules(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        settings.data_dir = Path(self._tmp.name)
        u._fails.clear()
        init_db()
        self.admin = u.create_user("ayse", "sifre123")          # ilk kullanıcı -> admin
        self.bob = u.create_user("bob", "sifre123", "user", self.admin.id)

    def tearDown(self):
        self._tmp.cleanup()

    def test_first_user_is_admin_and_hash_not_plain(self):
        self.assertEqual(self.admin.role, "admin")
        self.assertTrue(u.authenticate("AYSE", "sifre123").is_admin)  # büyük/küçük harf duyarsız

    def test_wrong_password(self):
        with self.assertRaises(u.AuthError):
            u.authenticate("ayse", "yanlis")

    def test_lockout(self):
        for _ in range(u.MAX_FAILS):
            with self.assertRaises(u.AuthError):
                u.authenticate("ayse", "yanlis")
        with self.assertRaises(u.AuthError):  # doğru şifre bile kilitliyken reddedilir
            u.authenticate("ayse", "sifre123")

    def test_user_cannot_manage(self):
        with self.assertRaises(u.PermissionDenied):
            u.create_user("x", "sifre123", "user", self.bob.id)
        with self.assertRaises(u.PermissionDenied):
            u.set_role(self.bob.id, self.bob.id, "admin")
        with self.assertRaises(u.PermissionDenied):
            u.list_users(self.bob.id)

    def test_cannot_demote_or_disable_last_admin(self):
        with self.assertRaises(u.RuleViolation):
            u.set_role(self.admin.id, self.admin.id, "user")
        with self.assertRaises(u.RuleViolation):
            u.set_active(self.admin.id, self.admin.id, False)

    def test_second_admin_allows_demotion(self):
        u.set_role(self.admin.id, self.bob.id, "admin")
        u.set_role(self.bob.id, self.admin.id, "user")
        self.assertFalse(u.authenticate("ayse", "sifre123").is_admin)
        with self.assertRaises(u.RuleViolation):  # artık bob son admin
            u.set_active(self.bob.id, self.bob.id, False)

    def test_transfer(self):
        u.transfer_admin(self.admin.id, self.bob.id)
        roles = {x.username: x.role for x in u.list_users(self.bob.id)}
        self.assertEqual(roles, {"ayse": "user", "bob": "admin"})

    def test_disabled_user_cannot_login(self):
        u.set_active(self.admin.id, self.bob.id, False)
        with self.assertRaises(u.AuthError):
            u.authenticate("bob", "sifre123")

    def test_duplicate_and_short_password(self):
        with self.assertRaises(ValueError):
            u.create_user("Bob", "sifre123", "user", self.admin.id)
        with self.assertRaises(ValueError):
            u.create_user("yeni", "123", "user", self.admin.id)


if __name__ == "__main__":
    unittest.main()
