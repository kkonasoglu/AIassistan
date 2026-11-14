"""Giriş / çıkış / ilk kurulum uç noktaları."""
import functools

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.api.deps import COOKIE, current_user
from app.services import sessions, users
from app.services.users import User

router = APIRouter(prefix="/auth")


class Credentials(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    current: str
    new: str


def user_json(u: User) -> dict:
    return {"id": u.id, "username": u.username, "role": u.role, "is_active": u.is_active}


def _login(response: Response, user: User) -> None:
    token = sessions.create(user.id)
    response.set_cookie(
        COOKIE, token, httponly=True, secure=True, samesite="strict",
        max_age=sessions.SESSION_HOURS * 3600, path="/",
    )


def map_errors(fn):
    """Servis hatalarını uygun HTTP koduna çevirir."""
    @functools.wraps(fn)  # FastAPI parametreleri bu sayede görebilir
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except users.AuthError as e:
            raise HTTPException(401, str(e))
        except users.PermissionDenied as e:
            raise HTTPException(403, str(e))
        except users.RuleViolation as e:
            raise HTTPException(409, str(e))
        except ConnectionError:
            raise HTTPException(503, "Yerel yapay zeka servisi (Ollama) çalışmıyor. "
                                     "Ollama'yı başlatıp tekrar deneyin.")
        except ValueError as e:
            raise HTTPException(400, str(e))
    return wrapper


@router.get("/state")
def state(request: Request):
    """Arayüzün hangi ekranı göstereceğini bilmesi için: kurulum gerekli mi, giriş var mı?"""
    token = request.cookies.get(COOKIE)
    user = sessions.resolve(token) if token else None
    return {"setup_needed": not users.has_any_user(),
            "user": user_json(user) if user else None}


@router.post("/setup")
@map_errors
def setup(body: Credentials, response: Response):
    """Yalnızca hiç kullanıcı yokken çalışır; ilk hesap admin olur.
    (Başka biri önce davranırsa create_user yetki hatası verir.)"""
    user = users.create_user(body.username, body.password)
    _login(response, user)
    return user_json(user)


@router.post("/login")
@map_errors
def login(body: Credentials, response: Response):
    user = users.authenticate(body.username, body.password)
    _login(response, user)
    return user_json(user)


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        sessions.destroy(token)
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_json(user)


@router.post("/password")
@map_errors
def change_own_password(body: PasswordChange, response: Response,
                        user: User = Depends(current_user)):
    users.authenticate(user.username, body.current)  # eski şifre doğru mu?
    users.change_password(user.id, user.id, body.new)
    sessions.destroy_all_for_user(user.id)           # diğer cihazlardaki oturumlar kapanır
    _login(response, user)
    return {"ok": True}
