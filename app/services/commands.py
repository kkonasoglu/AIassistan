"""Emir/komut anlama: "merhaba de", "sen kimsin", "saat kaç" gibi mesajlar (model gerektirmez, anında).

Kural: Dinyo bu tür isteklere "kayıt bulamadım" ya da "bunu yapamam" demez, yerine getirir.
Kodla yapıldığı için hızlıdır ve model uydurmaz.

İki grup vardır:
- quick_reply: kesin komutlar ("söyle", "de ki", "sen kimsin", "saat kaç"). Bilgi bankasına bakılmadan önce çalışır.
- weak_say: belirsiz biçimler ("X de", "X yaz"). "ve internet de" gibi sıradan cümlelerle karışabilir,
  bu yüzden YALNIZCA bilgi bankasında eşleşme yokken kullanılır.
"3. adımı tekrar yaz" gibi devam soruları (memory.looks_like_followup) komut sayılmaz.
"""
import datetime
import re
from typing import Callable

from app.services import intent, memory
from app.services.intent import norm

DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim",
          "Kasım", "Aralık"]

_QUOTES = " \"'“”‘’«»"
MAX_SAY = 200
MAX_WEAK_WORDS = 6

_STRONG = re.compile(r"^\s*(?:bana\s+)?(?P<x>.+?)\s+(?:diye\s+)?"
                     r"(?:söyle|söyler\s+misin|söyleyin|söyler\s+misiniz|söyleyebilir\s+misin)\s*[.!?]*\s*$",
                     re.I | re.S)
_PREFIX = re.compile(r"^\s*(?:(?:şunu|bunu)\s+(?:söyle|yaz|de|tekrar\s+et)|de\s+ki|şöyle\s+de|söyle)"
                     r"\s*[:\-,]?\s*(?P<x>.+)$", re.I | re.S)
_WEAK = re.compile(r"^\s*(?:bana\s+)?(?P<x>.+?)\s+(?:diye\s+)?"
                   r"(?:de|deyin|diyin|diyebilir\s+misin|yaz|yazar\s+mısın|yazın)\s*[.!?]*\s*$", re.I | re.S)
_CONJ = re.compile(r"\b(ve|ile|ama|veya|ancak|çünkü|fakat)\b", re.I)

_WHO = re.compile(r"\b(sen kimsin|kimsin sen|adın ne(dir)?|ismin ne(dir)?|adın nedir|kendini tanıt|sen nesin)\b")
_MYNAME = re.compile(r"\b(benim adım ne(dir)?|adım ne(dir)?|adımı (söyle|biliyor musun|hatırlıyor musun)|"
                     r"ben kimim|beni tanıyor musun|ismimi (söyle|biliyor musun))\b")
_CAN = re.compile(r"\b(ne yapabilirsin|neler yapabilirsin|ne işe yarıyorsun|neler biliyorsun|"
                  r"nasıl kullanılır|nasıl kullanırım|bana neler)\b|^(yardım|help)$")
_HELP = re.compile(r"\byardım(cı)? (et|eder misin|edebilir misin|eder misiniz|edermisin)\b")
_TIME = re.compile(r"\bsaat kaç\b|\bsaati söyle\b|\bşu an saat\b|\bsaat ne\b")
_DATE = re.compile(r"\bbugün günlerden\b|\bbugünün tarihi\b|\btarih(i)? (ne|nedir|söyle)\b|\bbugün ayın kaçı\b|"
                   r"\bbugün ne günü\b|\bhangi gündeyiz\b|\bbugün günlerden ne\b")
_REPEAT = re.compile(r"^(tekrar( et| söyle| edin| eder misin)?|tekrarla|bir daha( söyle| oku)?|yine söyle|ne dedin|"
                     r"baştan söyle)$")


def _now() -> datetime.datetime:         # testlerde değiştirilebilsin
    return datetime.datetime.now()


def _up(x: str) -> str:
    return x[:1].replace("i", "İ").replace("ı", "I").upper() + x[1:]


def _say(x: str) -> str | None:
    """Söylenmesi istenen metin: baş harf büyük, uygun noktalama ("merhaba" -> "Merhaba!")."""
    x = x.strip(_QUOTES + " ").strip()
    if not x or not re.search(r"\w", x) or len(x) > MAX_SAY:
        return None
    s = _up(x)
    if s[-1] not in ".!?…":
        s += "!" if (len(x.split()) <= 3 and intent.smalltalk(x) is not None) else "."
    return s


def _is_followup(text: str) -> bool:
    return memory.looks_like_followup(text)


def weak_say(text: str) -> str | None:
    """"merhaba de", "kolay gelsin yaz": belirsiz biçim, yalnızca bilgi bankasında eşleşme yokken."""
    if _is_followup(text):
        return None
    m = _WEAK.match(text)
    if not m:
        return None
    x = m.group("x")
    if len(x.split()) > MAX_WEAK_WORDS or _CONJ.search(x):
        return None
    return _say(x)


def _strong_say(text: str) -> str | None:
    m = _PREFIX.match(text)                  # "şunu söyle: ...", "de ki ..." içerik verilmiş, açık komut
    if m:
        return _say(m.group("x"))
    if _is_followup(text):                   # "3. adımı tekrar yaz" gibi devam soruları komut değildir
        return None
    m = _STRONG.match(text)
    return _say(m.group("x")) if m else None


def quick_reply(text: str, name: str, last_reply: Callable[[], str | None]) -> str | None:
    """Kesin komutlar ve küçük yardımcılar. Eşleşme yoksa None (normal akış sürer)."""
    t = norm(text).strip(" .!?,;:")
    if not t:
        return None
    if _REPEAT.match(t):
        return last_reply() or "Henüz tekrar edecek bir şey yok."
    if _WHO.search(t):
        return ("Ben Dinyo, ofisin teknik destek asistanıyım. Bilgi bankasındaki hata çözümlerini bulur, "
                "adım adım anlatır ve sesli okurum. Bilgi bankasında yoksa isterseniz internette de bakarım.")
    if _MYNAME.search(t):
        return (f"Size {name} diye hitap ediyorum. Değiştirmek isterseniz sağ üstteki adınıza tıklayabilirsiniz."
                if name else "Adınızı henüz bilmiyorum. Sağ üstteki kullanıcı adınıza tıklayıp yazabilirsiniz.")
    if _CAN.search(t):
        return ("Şunları yapabilirim: sorununuzu ya da hata kodunu yazın, bilgi bankasındaki çözümü hemen getireyim; "
                "cevabı sesli okurum (🔊); mikrofon düğmesiyle (F8) konuşarak da sorabilirsiniz; bilgi bankasında "
                "yoksa isterseniz internette ararım. Ayrıca \"merhaba de\" gibi isteklerinizi yerine getirir, "
                "saati ve tarihi söylerim. Yöneticiler \"bunu kaydet\" diyerek bilgi ekleyebilir.")
    if _HELP.search(t):
        return (f"Tabii {name}! " if name else "Tabii! ") + "Yaşadığınız sorunu ya da hata kodunu yazın, çözümü getireyim."
    if _TIME.search(t):
        return f"Saat {_now():%H:%M}."
    if _DATE.search(t):
        n = _now()
        return f"Bugün {n.day} {MONTHS[n.month - 1]} {n.year}, {DAYS[n.weekday()]}."
    return _strong_say(text)
