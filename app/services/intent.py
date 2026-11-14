"""Kısa, kural tabanlı mesaj anlama (model gerektirmez, anında).

Neden kural tabanlı? 3B model bu tür kesin kararlarda tutarsız kalabiliyor; selamlaşmaya
"kayıt bulamadım" demek de, teşekkürü uzun bir cevapla karşılamak da kötü deneyim.
"""
import re


def norm(text: str) -> str:
    """Türkçe büyük/küçük harf dönüşümünü doğru yaparak küçültür (İ->i, I->ı)."""
    return text.replace("İ", "i").replace("I", "ı").lower()


GREETING = "Merhaba! Size nasıl yardımcı olabilirim? Yaşadığınız sorunu veya hata kodunu yazmanız yeterli."
THANKS = "Rica ederim! Başka bir sorunuz olursa yazabilirsiniz."
HOW_ARE_YOU = "İyiyim, teşekkürler! Hangi konuda yardımcı olabilirim?"
ACK = "Tamamdır! Başka bir konuda yardımcı olabilirim."

_GREET = re.compile(r"^(merhaba|merhabalar|selam|selamlar|günaydın|iyi günler|iyi akşamlar|"
                    r"iyi çalışmalar|hey)\b")
_THANKS = re.compile(r"\b(teşekkür|sağ ?ol|eyvallah|saol)\w*")
_HOW = re.compile(r"\bnasılsın\b")
_ACK = {"tamam", "tamamdır", "anladım", "olur", "ok", "okey", "peki", "süper", "harika"}


def smalltalk(text: str) -> str | None:
    """Selamlaşma / teşekkür / onay ise hazır cevabı, değilse None döner.
    Yalnızca kısa mesajlarda ve bilgi bankasında eşleşme yokken kullanılır."""
    t = norm(text).strip(" .!?,;:")
    if not t or len(t.split()) > 6:
        return None
    if t in _ACK:
        return ACK
    if _THANKS.search(t):
        return THANKS
    if _HOW.search(t):
        return HOW_ARE_YOU
    if _GREET.match(t):
        return GREETING
    return None


# ---------------- Öğrenme komutu ("bunu kaydet") ----------------
# Komut KESİN ifadelerle tanınır; "Kaydet düğmesine basınca hata alıyorum" gibi sıradan
# cümleler komut sayılmaz.
_LEARN = re.compile(
    r"(?:\b(?:bunu|şunu|bu\s+bilgiyi|bu\s+çözümü|bu\s+hatayı)\s+"
    r"(?:(?:hafızaya|hafızana|bilgi\s*bankasına|sisteme)\s+)?(?:kaydet|kaydedin|öğren)\b"
    r"|\b(?:hafızaya|hafızana|bilgi\s*bankasına|sisteme)\s+(?:kaydet|kaydedin|ekle|al)\b"
    r"|^\s*(?:kaydet|öğren)\s*[:\-,]\s*)")
_BARE_LEARN = {"kaydet", "kaydedin", "öğren", "kaydet lütfen", "lütfen kaydet"}
_CONFIRM = {"evet", "onayla", "onaylıyorum", "kaydet", "kaydedin", "doğru", "evet kaydet",
            "evet onaylıyorum", "tamam kaydet", "evet doğru"}
_CANCEL = {"hayır", "hayir", "iptal", "iptal et", "vazgeç", "vazgeçtim", "kaydetme", "olmasın"}


def _clean_word(text: str) -> str:
    return norm(text).strip(" .!?,;:")


def parse_learn_command(text: str) -> str | None:
    """Mesaj bir öğrenme komutuysa, komut ifadesi çıkarılmış İÇERİĞİ döner ("" olabilir:
    "bunu kaydet" gibi, önceki mesaja gönderme). Komut değilse None."""
    t = norm(text)
    if _clean_word(text) in _BARE_LEARN:
        return ""
    m = _LEARN.search(t)
    if not m:
        return None
    # Komut ifadesini ORİJİNAL metinden çıkar (harf biçimi korunsun)
    content = text[:m.start()] + " " + text[m.end():]
    return " ".join(content.replace(" :", ":").split()).strip(" :-,")


def is_confirm(text: str) -> bool:
    return _clean_word(text) in _CONFIRM


def is_cancel(text: str) -> bool:
    return _clean_word(text) in _CANCEL


_TITLE = re.compile(r"^\s*(?:başlığı|başlık(?:\s+şu\s+olsun)?)\s*[:\-]\s*(.+)$", re.DOTALL)


def parse_title_override(text: str) -> str | None:
    """Onay bekleyen taslakta "başlık: Yeni başlık" -> "Yeni başlık". Yoksa None."""
    m = _TITLE.match(norm(text))
    if not m:
        return None
    return " ".join(text[m.start(1):m.end(1)].split()).strip(" .") or None
