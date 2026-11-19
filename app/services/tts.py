"""Sesli yanıt (metinden konuşmaya): Piper, sunucuda, CPU'da, çevrimdışı. Türkçe ERKEK ses (dfki).

Metin sunucuda sese çevrilip WAV olarak tarayıcıya gönderilir; hiçbir yere dışarı gönderilmez.
Ses modeli (~63 MB) ilk kullanımda indirilir (internet gerekir) ve data/models/tts altına kaydedilir;
klasör taşınınca model de taşınır, sonrasında internet gerekmez.

LİSANS UYARISI: varsayılan ses (tr_TR-dfki-medium) CC BY-NC-SA 4.0 lisanslıdır (ticari olmayan kullanım).
Şirket içi kullanımın bu kapsama girip girmediğine kullanıcı karar vermelidir; sesi değiştirmek için
OFIS_TTS_VOICE ayarına başka bir Piper sesi yazılır.
"""
import io
import re
import threading
import wave

from app.core.config import settings

_voice = None
_lock = threading.Lock()
HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


class ModelUnavailable(Exception):
    """Ses modeli yüklenemedi (ör. ilk kurulumda internet yok)."""


def _model_files():
    d = settings.tts_dir
    return d / f"{settings.tts_voice}.onnx", d / f"{settings.tts_voice}.onnx.json"


def _download() -> None:
    """Modeli Hugging Face'ten indirir (yalnızca ilk kullanımda, dosya yoksa)."""
    import httpx
    lang, name, quality = settings.tts_voice.split("-")
    base = f"{HF}/{lang.split('_')[0]}/{lang}/{name}/{quality}/{settings.tts_voice}"
    settings.tts_dir.mkdir(parents=True, exist_ok=True)
    for dest, url in zip(_model_files(), (base + ".onnx", base + ".onnx.json")):
        if dest.exists():
            continue
        tmp = dest.with_suffix(dest.suffix + ".part")
        with httpx.stream("GET", url, follow_redirects=True, timeout=60) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        tmp.replace(dest)


def _load():
    from piper import PiperVoice
    onnx, cfg = _model_files()
    if not (onnx.exists() and cfg.exists()):
        _download()
    return PiperVoice.load(str(onnx), config_path=str(cfg))


def get_voice():
    global _voice
    with _lock:
        if _voice is None:
            try:
                _voice = _load()
            except Exception as e:
                raise ModelUnavailable(str(e)) from e
        return _voice


def is_loaded() -> bool:
    return _voice is not None


def preload() -> None:
    def work():
        try:
            get_voice()
        except ModelUnavailable:
            pass
    threading.Thread(target=work, daemon=True, name="tts-preload").start()


# ---------- metni sesli okunacak hale getir ----------
_URL = re.compile(r"https?://\S+")
_CODE = re.compile(r"\b([A-Za-z]{2,6})\s*-\s*(\d{2,5})\b")          # KNK-204 -> "K N K, 204"
_MARK = re.compile(r"[*_`#>|~\[\]{}<]+")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]")
_STEP = re.compile(r"(?m)^\s*(\d{1,2})[.)]\s+")


def clean_for_speech(text: str, limit: int | None = None) -> str:
    """Biçimlendirmeyi, bağlantıları ve simgeleri atar; hata kodlarını harf harf okunur yapar;
    uzunsa cümle sınırından keser."""
    limit = limit or settings.tts_max_chars
    t = _URL.sub(" ", text)
    t = _EMOJI.sub(" ", t)
    t = _MARK.sub(" ", t)
    t = _CODE.sub(lambda m: f"{' '.join(m.group(1).upper())}, {m.group(2)}", t)
    t = _STEP.sub(lambda m: f"{m.group(1)}. adım: ", t)
    t = re.sub(r"\s*\n+\s*", ". ", t)                                  # satır sonu = kısa durak
    t = re.sub(r"([.!?…:;])\s*\.", r"\1", t)
    t = re.sub(r"\s+", " ", t).strip(" .")
    if len(t) > limit:
        cut = t[:limit]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        t = (cut[:end + 1] if end > limit * 0.5 else cut.rsplit(" ", 1)[0]).strip()
    return t


VOICES = ("male", "female")


def _raise_pitch(wav: bytes, factor: float) -> bytes:
    """Aynı örnekleri daha yüksek örnekleme hızı etiketiyle yazar: ses tizleşir ve hızlanır
    (hız, sentezde length_scale ile önceden dengelenir). Ek kütüphane gerekmez."""
    with wave.open(io.BytesIO(wav), "rb") as r:
        params, frames = r.getparams(), r.readframes(r.getnframes())
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(params.nchannels)
        w.setsampwidth(params.sampwidth)
        w.setframerate(int(params.framerate * factor))
        w.writeframes(frames)
    return out.getvalue()


def synthesize(text: str, gender: str = "male") -> bytes:
    """Metni WAV'a çevirir. gender: "male" (doğal) | "female" (yükseltilmiş perde).
    Okunacak bir şey kalmazsa b"" döner."""
    speech = clean_for_speech(text)
    if not re.search(r"\w", speech):
        return b""
    voice = get_voice()
    from piper import SynthesisConfig
    pitch = settings.tts_female_pitch if gender == "female" else 1.0
    cfg = SynthesisConfig(length_scale=settings.tts_length_scale * pitch)   # tizleşince hızlanan sesi yavaşlat
    buf = io.BytesIO()
    with _lock:                                  # tek motor örneği: aynı anda tek sentez
        with wave.open(buf, "wb") as w:
            voice.synthesize_wav(speech, w, syn_config=cfg)
    wav = buf.getvalue()
    return _raise_pitch(wav, pitch) if pitch != 1.0 else wav
