from fastapi import APIRouter

from app.core.config import settings
from app.services import llm, rag, stt

router = APIRouter()


@router.get("/health")
def health():
    """Sunucu ve Ollama durumu. Gizli bilgi içermez."""
    return {"ok": True, "model": settings.llm_model, "kb_count": rag.count(), "stt_loaded": stt.is_loaded(), **llm.status()}
