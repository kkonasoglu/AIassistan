"""FastAPI uygulaması. Sunucuyu `python run.py` başlatır."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.api import admin, auth, chat, health, voice
from app.api.deps import csrf_guard
from app.core.config import settings
from app.db.database import init_db
from app.services import stt

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # tablolar yoksa oluşturur
    if settings.stt_preload:
        stt.preload()  # konuşma modelini arka planda yükle
    yield


app = FastAPI(title="Ofis Asistanı", lifespan=lifespan, docs_url=None, redoc_url=None)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# Tüm /api yollarında CSRF koruması (değiştiren isteklerde özel başlık şartı)
api = APIRouter(prefix="/api", dependencies=[Depends(csrf_guard)])
api.include_router(health.router)
api.include_router(auth.router)
api.include_router(admin.router)
api.include_router(chat.router)
api.include_router(voice.router)
app.include_router(api)

# En sonda statik sayfalar (aksi halde "/" her şeyi yakalar)
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
