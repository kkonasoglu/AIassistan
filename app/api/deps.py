"""Ortak bağımlılıklar: kimlik, yetki, CSRF koruması."""
from fastapi import HTTPException, Request

from app.services import sessions
from app.services.users import User

COOKIE = "ofis_session"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def csrf_guard(request: Request) -> None:
    """Değiştiren isteklerde özel başlık zorunlu. Başka bir sitedeki form/istek bu
    başlığı ekleyemez (çerez ayrıca SameSite=Strict). Çapraz site isteği (CSRF) engellenir."""
    if request.method not in SAFE_METHODS and request.headers.get("x-requested-with") != "fetch":
        raise HTTPException(403, "Geçersiz istek.")


def current_user(request: Request) -> User:
    token = request.cookies.get(COOKIE)
    user = sessions.resolve(token) if token else None
    if not user:
        raise HTTPException(401, "Giriş yapmanız gerekiyor.")
    return user


def require_admin(request: Request) -> User:
    user = current_user(request)
    if not user.is_admin:
        raise HTTPException(403, "Bu işlem için admin yetkisi gerekir.")
    return user
