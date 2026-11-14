"""Sunucu tarafı oturumlar.

Tarayıcıya rastgele bir jeton veririz (çerezde). Veritabanında jetonun kendisini
değil SHA-256 özetini saklarız; veritabanı sızsa bile jeton ele geçirilemez.

Neden sunucuda tutuyoruz? Kullanıcı pasife alınınca ya da rolü değişince etkisi
ANINDA olsun diye: her istekte kullanıcı veritabanından taze okunur.
"""
import hashlib
import secrets

from app.db.database import transaction
from app.services.users import User

SESSION_HOURS = 12


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with transaction() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= datetime('now')")  # süpür
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) "
            "VALUES (?, ?, datetime('now', ?))",
            (_hash(token), user_id, f"+{SESSION_HOURS} hours"),
        )
    return token


def resolve(token: str) -> User | None:
    """Geçerli oturumun sahibini döner. Süresi dolmuş veya pasif hesapsa None."""
    with transaction() as conn:
        row = conn.execute(
            "SELECT u.id, u.username, u.role, u.is_active FROM sessions s "
            "JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = ? AND s.expires_at > datetime('now')",
            (_hash(token),),
        ).fetchone()
    if not row or not row["is_active"]:
        return None
    return User(row["id"], row["username"], row["role"], True)


def destroy(token: str) -> None:
    with transaction() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash(token),))


def destroy_all_for_user(user_id: int) -> None:
    with transaction() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
