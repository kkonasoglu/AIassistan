"""Kısa süreli hafıza: kayan pencere.

Neden? Tüm geçmişi her seferinde modele göndermek CPU'da cevabı yavaşlatır ve
modelin bağlam sınırını doldurur. Son N soru-cevap çiftini veririz; fazla uzunsa
en eski mesajlar atılır. Tam geçmiş yine veritabanında durur, ekranda görünür.

Bir asistan mesajı "kartlar (bilgi bankası kayıtları) + not" içerir. Modele ve adım
çıkarmaya giderken ikisi tek metin olarak birleştirilir.
"""
import re

from app.core.config import settings
from app.services import chat_store
from app.services.intent import norm

# Devam sorusu ifadeleri: "3. adımı tekrar yaz", "bunu açıkla", "peki neden?"
_FOLLOWUP_STEMS = re.compile(
    r"\b(adım|madde|açıkla|detay|ayrıntı|özetle|kısalt|basitleştir|önceki|yukarıdaki|"
    r"tekrar|devam|peki|anlamadım|örnek)\w*")
_FOLLOWUP_WORDS = re.compile(
    r"\b(bu|şu|bunu|şunu|bunun|şunun|buna|şuna|bundan|şundan|o|onu|onun|neden|niye)\b")

_ORDINALS = {"ilk": 1, "birinci": 1, "ikinci": 2, "üçüncü": 3, "dördüncü": 4,
             "beşinci": 5, "altıncı": 6, "yedinci": 7, "sekizinci": 8}
_STEP_NUM = re.compile(r"\b(\d{1,2})\s*\.?\s*(?:adım|madde)")
_STEP_WORD = re.compile(r"\b(" + "|".join(_ORDINALS) + r")\s+(?:adım|madde)")


def requested_step(text: str) -> int | None:
    """"3. adımı tekrar yaz", "ikinci adımı açıkla" -> 3, 2. Yoksa None."""
    t = norm(text)
    m = _STEP_NUM.search(t)
    if m:
        return int(m.group(1))
    m = _STEP_WORD.search(t)
    return _ORDINALS[m.group(1)] if m else None


def step_from_previous(history: list[dict], text: str) -> str | None:
    """İstenen adımı önceki cevaptan KOD ile alır. Küçük model bu işte güvenilmezdi:
    yalnızca o adımı değil tüm çözümü yeniden yazıyordu."""
    n = requested_step(text)
    if n is None:
        return None
    previous = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), "")
    for line in previous.splitlines():
        m = re.match(rf"^\s*{n}[.)]\s*(.+)$", line)
        if m:
            return f"{n}. {m.group(1).strip()}"
    return None


def looks_like_followup(text: str) -> bool:
    """Soru, önceki cevaba gönderme yapıyor gibi mi? (Kod karar verir; modele bırakılmaz.)
    Alakasız sorularda ("Pizza nasıl yapılır?") modelin kendi bilgisinden uydurmasını önler."""
    t = norm(text)
    return len(t.split()) <= 20 and bool(_FOLLOWUP_STEMS.search(t) or _FOLLOWUP_WORDS.search(t))


def _flatten(msg: dict) -> dict:
    """Kartları (bilgi bankası kayıtları) mesaj metnine katar: model ve adım çıkarma
    önceki cevabın TAM halini görsün."""
    content = msg["content"]
    cards = msg.get("cards") or []
    if cards:
        blocks = "\n\n".join(f"{c['title']}\n{c['solution']}" for c in cards)
        content = f"{blocks}\n\n{content}".strip()
    return {"role": msg["role"], "content": content}


def window(user_id: int, conv_id: int) -> list[dict]:
    msgs = [_flatten(m) for m in
            chat_store.recent_messages(user_id, conv_id, settings.history_turns * 2 + 1)]
    # Pencere her zaman bir "user" mesajıyla başlasın (yarım çift kalmasın)
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    # Karakter bütçesini aşıyorsa en eskiden at; son mesaj her zaman kalır
    while len(msgs) > 1 and sum(len(m["content"]) for m in msgs) > settings.max_history_chars:
        msgs.pop(0)
        while msgs and msgs[0]["role"] != "user" and len(msgs) > 1:
            msgs.pop(0)
    return msgs
