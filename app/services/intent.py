"""Kısa, kural tabanlı mesaj anlama (model gerektirmez, anında).

Neden kural tabanlı? 3B model bu tür kesin kararlarda tutarsız kalabiliyor; selamlaşmaya
"kayıt bulamadım" demek de, teşekkürü uzun bir cevapla karşılamak da kötü deneyim.
"""
import random
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
_HOW = re.compile(r"\b(nasılsın|nasılsınız|naber|ne haber|nasıl gidiyor|iyi misin|ne var ne yok|keyfin nasıl)\b")
_ACK = {"tamam", "tamamdır", "anladım", "olur", "ok", "okey", "peki", "süper", "harika"}


# Günlük sohbet: kısa, kurallı, uydurma riski olmayan cevaplar (birden çok seçenekten biri rastgele seçilir).
# Sıra önemlidir: önce özel (kızgınlık, veda), sonra genel. Ad hitabı personalize() ile eklenir.
_ME = r"(?:ben de |ben |çok |gayet )?"
_EXTRAS = [
    (re.compile(r"\b(aptal|salak|geri zekalı|işe yaramaz|rezil|zeki değil|anlamıyorsun|bir şey bilmiyorsun|beceriksiz)\w*"),
     ["Üzgünüm, yeterince yardımcı olamadım! Sorunu biraz farklı yazarsanız tekrar deneyeyim.",
      "Haklısınız, daha iyisini yapmalıyım! Hata kodunu ya da sorunu başka kelimelerle yazar mısınız?"]),
    (re.compile(r"\b(görüşürüz|hoşça ?kal|bay bay|bye|güle güle|iyi geceler|kendine iyi bak|ben çıkıyorum|ben gidiyorum)\b"),
     ["Görüşmek üzere!", "Hoşça kalın, iyi çalışmalar!", "Görüşürüz, ihtiyacınız olursa buradayım!"]),
    (re.compile(r"\bkolay gelsin\b"), ["Size de kolay gelsin!", "Sağ olun, size de kolay gelsin!"]),
    (re.compile(r"\b(ne yapıyorsun|napıyorsun|ne yapıyosun|napıyosun|neyle meşgulsün)\b"),
     ["Sizi bekliyordum! Bir sorun ya da hata kodu yazarsanız hemen bakarım.",
      "Buradayım, sorularınızı bekliyorum!"]),
    (re.compile(r"\b(orada mısın|burada mısın|duyuyor musun|var mısın|uyuyor musun|uyudun mu|uyandın mı)\b"),
     ["Buradayım! Dinliyorum.", "Evet, buradayım! Nasıl yardımcı olabilirim?"]),
    (re.compile(r"\b(seni seviyorum|sevdim seni|canım benim|tatlısın|sevimlisin)\b"),
     ["Çok naziksiniz! Ben de size yardımcı olmaktan memnunum.", "Ne güzel söylediniz! Teşekkür ederim."]),
    (re.compile(r"\b(aferin|bravo|helal|çok iyisin|harikasın|süpersin|akıllısın|zekisin|çok güzel|mükemmel|beğendim)\b"),
     ["Teşekkür ederim, çok naziksiniz!", "Sağ olun, elimden geleni yapıyorum!"]),
    (re.compile(r"^(?:" + _ME + r")?(iyiyim|iyi|fena değil|idare eder|harikayım|gayet iyi)(?: dinyo)?$"),
     ["Sevindim! Size nasıl yardımcı olabilirim?", "Ne güzel! Bir sorun varsa buradayım."]),
    (re.compile(r"\b(kötüyüm|yorgunum|moralim bozuk|canım sıkkın|bunaldım|sıkıldım|çok yoruldum)\b"),
     ["Geçmiş olsun! İsterseniz birlikte bakalım, sorunu yazın.", "Üzüldüm. Elimden geliyorsa sorununuzu çözmeye çalışırım."]),
    (re.compile(r"^(ha){2,}h?$|^(he){2,}h?$|\bkomik\b"), ["😄 Başka bir konuda yardımcı olabilir miyim?"]),
]


def _extra(t: str) -> str | None:
    for pattern, replies in _EXTRAS:
        if pattern.search(t):
            return random.choice(replies)
    return None


def display_name(username: str) -> str:
    """Hitap için kullanıcı adının baş harfi büyütülür (Türkçe i/ı kuralıyla): ayse -> Ayse."""
    u = username.strip()
    first = u[:1].replace("i", "İ").replace("ı", "I").upper()
    return first + u[1:]


def personalize(reply: str, username: str) -> str:
    """Hazır selamlaşma cevabındaki ilk ünleme kullanıcının adı eklenir: "Merhaba!" -> "Merhaba Ayse!"."""
    return reply.replace("!", f" {display_name(username)}!", 1)


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
    return _extra(t)


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


_WEB_YES = {"evet", "ara", "araştır", "olur", "tamam", "tamamdır", "ok", "okey", "evet ara", "evet araştır",
            "evet lütfen", "lütfen", "ara lütfen", "araştır lütfen", "internetten ara", "internette ara",
            "evet isterim", "isterim", "istiyorum", "evet olur", "tamam ara", "evet ister"}
_WEB_NO = {"hayır", "hayir", "yok", "gerek yok", "istemiyorum", "istemem", "olmasın", "vazgeç", "iptal",
           "hayır teşekkürler", "hayır istemiyorum", "hayır gerek yok", "yok gerek yok"}


def is_web_yes(text: str) -> bool:
    """"İnternette aramamı ister misiniz?" sorusuna olumlu cevap."""
    return _clean_word(text) in _WEB_YES


def is_web_no(text: str) -> bool:
    return _clean_word(text) in _WEB_NO


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
