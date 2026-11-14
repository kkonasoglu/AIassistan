"""Konuşma tanıma (bas-konuş): faster-whisper, sunucuda, CPU'da, çevrimdışı.

Ses tarayıcıda kaydedilir, sunucuya gelir, geçici dosyada çözülür, metne çevrilir ve
dosya HEMEN silinir. Ses ve metin hiçbir yere gönderilmez.

Model ilk kullanımda indirilir (internet gerekir) ve data/models altına kaydedilir; klasör
taşınınca model de taşınır, sonrasında internet gerekmez.
"""
import os
import threading

from app.core.config import settings

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # Windows'ta gereksiz uyarı

_model = None
_lock = threading.Lock()


class ModelUnavailable(Exception):
    """Konuşma tanıma modeli yüklenemedi (ör. ilk kurulumda internet yok)."""


def _load():
    from faster_whisper import WhisperModel
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    return WhisperModel(settings.stt_model, device="cpu", compute_type="int8",
                        cpu_threads=settings.stt_threads, download_root=str(settings.models_dir))


def get_model():
    global _model
    with _lock:
        if _model is None:
            try:
                _model = _load()
            except Exception as e:  # indirme/yükleme hatası
                raise ModelUnavailable(str(e)) from e
        return _model


def is_loaded() -> bool:
    return _model is not None


def preload() -> None:
    """Modeli arka planda yükler; hata olursa sessizce geçer (ilk istekte tekrar denenir)."""
    def work():
        try:
            get_model()
        except ModelUnavailable:
            pass
    threading.Thread(target=work, daemon=True, name="stt-preload").start()


def transcribe(path: str) -> str:
    """Ses dosyasını (webm/ogg/mp4/wav...) Türkçe metne çevirir. Sessizlikte "" döner."""
    model = get_model()
    kwargs = {"hotwords": settings.stt_hotwords} if settings.stt_hotwords else {}
    segments, _ = model.transcribe(
        path, language=settings.stt_language, beam_size=1,
        vad_filter=True,                     # sessiz kısımları atar (hem hız, hem uydurma önler)
        condition_on_previous_text=False, **kwargs)
    return " ".join(s.text.strip() for s in segments).strip()
