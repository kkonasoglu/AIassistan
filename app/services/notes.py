"""Kartın üstündeki kısa not.

İki kaynak: hazır şablon (anında, risksiz) veya model (çıktısı doğrulanır).
Model notu geçersizse şablona dönülür; kullanıcı asla bozuk/uydurma not görmez.
"""
import re

_CODE = re.compile(r"\b([A-Za-z]{2,6})-?(\d{2,5})\b")
_CJK = re.compile(r"[぀-ヿ一-鿿]")
_NUMBERED_LINE = re.compile(r"(?m)^\s*\d+[.)]\s")
MAX_NOTE_CHARS = 300


def template_note(hits: list[dict]) -> str:
    if len(hits) == 1:
        return (f'Anladım, bu sorun "{hits[0]["title"]}" kaydıyla eşleşiyor. '
                "Aşağıdaki adımları sırayla deneyin; olmazsa bana yazın.")
    return (f"Sorununuzla ilgili {len(hits)} kayıt buldum. En uygun olandan başlayarak "
            "adımları sırayla deneyin; olmazsa bana yazın.")


def _codes(text: str) -> set[str]:
    return {f"{a.upper()}-{b}" for a, b in _CODE.findall(text)}


def clean_llm_note(note: str, hits: list[dict]) -> str | None:
    """Model notunu doğrular. Geçerliyse temizlenmiş notu, değilse None döner.

    Reddedilenler: boş, çok uzun, Çince/Japonca karakter, adım listesi (adımlar kartta
    zaten var), kayıtlarda geçmeyen hata kodu (uydurma), cümlesi yarıda kesilmiş not.
    """
    note = note.strip()
    if not note or len(note) > MAX_NOTE_CHARS or _CJK.search(note):
        return None
    if _NUMBERED_LINE.search(note):
        return None
    known = _codes(" ".join(h["text"] for h in hits))
    if not _codes(note) <= known:
        return None
    if note[-1] not in ".!?":  # yarıda kesilmiş: son tam cümleye kadar al
        cut = max(note.rfind("."), note.rfind("!"), note.rfind("?"))
        if cut < 0:
            return None
        note = note[: cut + 1]
    return note
