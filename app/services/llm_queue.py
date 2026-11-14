"""Modele giden istekleri sıraya alır.

CPU'da model aynı anda genelde tek isteği iyi işler. Birkaç kişi aynı anda sorarsa
herkes aynı anda yavaşlamasın diye sırayla işleriz ve bekleyene sırasını söyleriz.
"""
import asyncio
from contextlib import asynccontextmanager

from app.core.config import settings

_sem: asyncio.Semaphore | None = None
_waiting = 0


def waiting_count() -> int:
    return _waiting


def position_if_wait() -> int:
    """Şimdi girersek beklememiz gerekiyor mu? Gerekiyorsa sıra numaramız, yoksa 0."""
    if _sem is not None and _sem.locked():
        return _waiting + 1
    return 0


def reset() -> None:
    """Testler için."""
    global _sem, _waiting
    _sem, _waiting = None, 0


@asynccontextmanager
async def slot(on_wait=None):
    """`async with slot(): ...` içinde model çalıştırılır.
    Sıra doluysa on_wait(sıra_numarası) çağrılır, sonra yer açılınca devam edilir."""
    global _sem, _waiting
    if _sem is None:
        _sem = asyncio.Semaphore(settings.max_concurrent_llm)
    if _sem.locked():
        _waiting += 1
        try:
            if on_wait:
                await on_wait(_waiting)
            await _sem.acquire()
        finally:
            _waiting -= 1
    else:
        await _sem.acquire()
    try:
        yield
    finally:
        _sem.release()
