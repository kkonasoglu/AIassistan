"""Bas-konuş: tarayıcıdan gelen kısa ses kaydını metne çevirir.

Gövde ham ses verisidir (Content-Type: audio/webm gibi). Giriş yapmış herkes sorusunu sesle
sorabilir. "Bunu kaydet" gibi yetki gerektiren komutlar yine sohbet katmanında admin
kontrolünden geçer: ses yalnızca metne çevrilir, ek yetki vermez.
"""
import asyncio
import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import current_user
from app.core.config import settings
from app.services import llm_queue, stt
from app.services.users import User

router = APIRouter(prefix="/voice")

_EXT = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".mp4", "audio/mpeg": ".mp3",
        "audio/wav": ".wav", "audio/x-wav": ".wav"}
MIN_BYTES = 1000   # bundan küçük kayıt anlamlı bir ses değildir


@router.post("/transcribe")
async def transcribe(request: Request, user: User = Depends(current_user)):
    ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if ctype not in _EXT:
        raise HTTPException(415, "Desteklenmeyen ses biçimi.")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.stt_max_bytes:
        raise HTTPException(413, "Ses kaydı çok büyük.")
    data = bytearray()
    async for chunk in request.stream():       # gövdeyi sınırı aşmadan oku
        data.extend(chunk)
        if len(data) > settings.stt_max_bytes:
            raise HTTPException(413, "Ses kaydı çok büyük.")
    if len(data) < MIN_BYTES:
        return {"text": ""}

    fd, path = tempfile.mkstemp(suffix=_EXT[ctype], prefix="ofis-ses-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        loop = asyncio.get_running_loop()
        async with llm_queue.slot():           # model ve konuşma tanıma aynı CPU'yu paylaşır: sıraya gir
            text = await loop.run_in_executor(None, stt.transcribe, path)
    except stt.ModelUnavailable:
        raise HTTPException(503, "Konuşma tanıma modeli yüklenemedi. İlk kurulumda modelin indirilmesi "
                                 "için sunucunun internete bağlı olması gerekir.")
    except Exception:
        raise HTTPException(400, "Ses kaydı çözülemedi. Tekrar deneyin.")
    finally:
        try:
            os.unlink(path)                    # ses kaydı hiçbir koşulda diskte kalmaz
        except OSError:
            pass
    return {"text": text}
