"""Kullanıcı hesapları, roller ve yetki kuralları.

Yetki kontrolü BURADA yapılır (arayüzde değil). Her yönetim fonksiyonu, işlemi
yapan kişinin (actor) rolünü veritabanından taze okur; arayüzden gelen bilgiye
güvenmez.

Güvenlik kuralı: sistemde her zaman en az 1 AKTİF admin kalır.
"""
import sqlite3
import time
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.db.database import transaction

ROLES = ("admin", "user")
MIN_PASSWORD_LEN = 6
MAX_NAME_LEN = 40
MAX_FAILS = 5
LOCK_SECONDS = 30

_ph = PasswordHasher()
_fails: dict[str, tuple[int, float]] = {}  # kullanıcı adı -> (hata sayısı, kilit bitişi)


class PermissionDenied(Exception):
    """Bu işlem için yetkiniz yok."""


class RuleViolation(Exception):
    """Güvenlik/iş kuralına aykırı işlem (örn. son admin)."""


class AuthError(Exception):
    """Giriş başarısız."""


@dataclass(frozen=True)
class User:
    id: int
    username: str
    role: str
    is_active: bool
    display_name: str = ""

    @property
    def call_name(self) -> str:
        """Hitap adı: görünen adın ilk sözcüğü ("Kerem Konasoğlu" -> "Kerem"); yoksa kullanıcı adı."""
        parts = self.display_name.split()
        base = parts[0] if parts else self.username
        return base[:1].replace("i", "İ").replace("ı", "I").upper() + base[1:]

    @property
    def is_admin(self) -> bool:
        return self.role == "admin" and self.is_active


def _to_user(row) -> User:
    return User(row["id"], row["username"], row["role"], bool(row["is_active"]), row["display_name"])


def _validate(username: str, password: str | None = None, role: str | None = None):
    if not username.strip():
        raise ValueError("Kullanıcı adı boş olamaz.")
    if password is not None and len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"Şifre en az {MIN_PASSWORD_LEN} karakter olmalı.")
    if role is not None and role not in ROLES:
        raise ValueError("Geçersiz rol.")


def _active_admin_count(conn) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1"
    ).fetchone()[0]


def _require_admin(conn, actor_id: int) -> None:
    row = conn.execute("SELECT role, is_active FROM users WHERE id=?", (actor_id,)).fetchone()
    if not row or row["role"] != "admin" or not row["is_active"]:
        raise PermissionDenied("Bu işlem için admin yetkisi gerekir.")


def _get(conn, user_id: int):
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        raise ValueError("Kullanıcı bulunamadı.")
    return row


def clean_display_name(name: str) -> str:
    """Görünen ad (hitap için): boşlukları düzenler, çok uzunsa reddeder. Boş olabilir."""
    name = " ".join((name or "").split())
    if len(name) > MAX_NAME_LEN:
        raise ValueError(f"Ad en fazla {MAX_NAME_LEN} karakter olabilir.")
    return name


# ---------- sorgular ----------
def has_any_user() -> bool:
    with transaction() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0


def get_user(user_id: int) -> User:
    with transaction() as conn:
        return _to_user(_get(conn, user_id))


def list_users(actor_id: int) -> list[User]:
    with transaction() as conn:
        _require_admin(conn, actor_id)
        return [_to_user(r) for r in conn.execute("SELECT * FROM users ORDER BY username")]


# ---------- oluşturma / giriş ----------
def create_user(username: str, password: str, role: str = "user",
                actor_id: int | None = None, display_name: str = "") -> User:
    """Kullanıcı oluşturur. Hiç kullanıcı yoksa (ilk kurulum) kimlik gerekmez ve
    hesap otomatik admin olur. Sonrasında yalnızca admin kullanıcı ekleyebilir."""
    username = username.strip()
    _validate(username, password, role)
    display_name = clean_display_name(display_name)
    with transaction() as conn:
        first = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        if first:
            role = "admin"
        else:
            if actor_id is None:
                raise PermissionDenied("Bu işlem için admin yetkisi gerekir.")
            _require_admin(conn, actor_id)
        try:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, role, display_name) VALUES (?, ?, ?, ?)",
                (username, _ph.hash(password), role, display_name),
            )
        except sqlite3.IntegrityError:
            raise ValueError("Bu kullanıcı adı zaten var.") from None
        return _to_user(_get(conn, cur.lastrowid))


def authenticate(username: str, password: str) -> User:
    """Başarılıysa User döner, değilse AuthError. Mesaj bilerek genel tutulur
    (kullanıcı adının var olup olmadığı sızdırılmaz)."""
    key = username.strip().lower()
    fails, locked_until = _fails.get(key, (0, 0.0))
    if locked_until > time.time():
        raise AuthError(f"Çok fazla hatalı deneme. {int(locked_until - time.time()) + 1} sn bekleyin.")

    with transaction() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username.strip(),)).fetchone()
    ok = False
    if row and row["is_active"]:
        try:
            ok = _ph.verify(row["password_hash"], password)
        except (VerifyMismatchError, InvalidHashError):
            ok = False
    if not ok:
        fails += 1
        if fails >= MAX_FAILS:  # kilitle ve sayacı sıfırla
            _fails[key] = (0, time.time() + LOCK_SECONDS)
        else:
            _fails[key] = (fails, 0.0)
        raise AuthError("Kullanıcı adı veya şifre hatalı.")
    _fails.pop(key, None)
    return _to_user(row)


def change_password(actor_id: int, target_id: int, new_password: str) -> None:
    """Kişi kendi şifresini, admin herkesinkini değiştirebilir."""
    _validate("x", new_password)
    with transaction() as conn:
        if actor_id != target_id:
            _require_admin(conn, actor_id)
        _get(conn, target_id)
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (_ph.hash(new_password), target_id))


def set_display_name(actor_id: int, target_id: int, name: str) -> str:
    """Kişi kendi adını, admin herkesinkini değiştirebilir. Dinyo bu adla hitap eder."""
    name = clean_display_name(name)
    with transaction() as conn:
        if actor_id != target_id:
            _require_admin(conn, actor_id)
        _get(conn, target_id)
        conn.execute("UPDATE users SET display_name=? WHERE id=?", (name, target_id))
    return name


# ---------- rol / durum yönetimi ----------
def set_role(actor_id: int, target_id: int, role: str) -> None:
    _validate("x", role=role)
    with transaction() as conn:
        _require_admin(conn, actor_id)
        target = _get(conn, target_id)
        is_active_admin = target["role"] == "admin" and target["is_active"]
        if role == "user" and is_active_admin and _active_admin_count(conn) <= 1:
            raise RuleViolation("Sistemde en az 1 aktif admin kalmalı.")
        conn.execute("UPDATE users SET role=? WHERE id=?", (role, target_id))


def set_active(actor_id: int, target_id: int, active: bool) -> None:
    """Hesabı pasife alır / yeniden açar. Pasif hesap giriş yapamaz.
    ('Silme' = pasife alma; kayıt veritabanında kalır.)"""
    with transaction() as conn:
        _require_admin(conn, actor_id)
        target = _get(conn, target_id)
        is_active_admin = target["role"] == "admin" and target["is_active"]
        if not active and is_active_admin and _active_admin_count(conn) <= 1:
            raise RuleViolation("Sistemde en az 1 aktif admin kalmalı.")
        conn.execute("UPDATE users SET is_active=? WHERE id=?", (int(active), target_id))


def transfer_admin(actor_id: int, target_id: int) -> None:
    """Admin rolünü başkasına devreder. Tek işlemde: önce hedef admin yapılır,
    sonra devreden user olur; sistem hiçbir anda adminsiz kalmaz."""
    with transaction() as conn:
        _require_admin(conn, actor_id)
        if actor_id == target_id:
            raise ValueError("Kendinize devredemezsiniz.")
        target = _get(conn, target_id)
        if not target["is_active"]:
            raise RuleViolation("Pasif bir hesaba yetki devredilemez.")
        conn.execute("UPDATE users SET role='admin' WHERE id=?", (target_id,))
        conn.execute("UPDATE users SET role='user' WHERE id=?", (actor_id,))
