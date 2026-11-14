"""İnternet araması (DuckDuckGo). Yalnızca bilgi bankasında cevap bulunamayınca kullanılır.

Dışarı yalnızca kullanıcının o anki sorusu gider (temizlenmiş halde); bilgi bankası içeriği,
sohbet geçmişi ve kullanıcı adı ASLA gönderilmez. Sonuçlar modele özetlettirilmez
(küçük model uydurur): başlık, kısa özet ve bağlantı birebir gösterilir.
"""
import logging
import re
import time

from app.core.config import settings

log = logging.getLogger("ofis.web")

_EMAIL = re.compile(r"\S+@\S+\.\S+")
_LONG_NUMBER = re.compile(r"\d[\d\s.\-/]{5,}\d")     # vergi no, TC no, telefon, IBAN parçası vb.
MAX_QUERY = 200


def sanitize(text: str) -> str:
    """Kişisel/kurumsal veri olabilecek kısımları aramadan önce siler."""
    q = _EMAIL.sub(" ", text)
    q = _LONG_NUMBER.sub(" ", q)
    return re.sub(r"\s+", " ", q).strip()[:MAX_QUERY]


def search(text: str) -> list[dict]:
    """[{title, snippet, url}] döner; internet yok/hata/boş sorgu durumunda []."""
    query = sanitize(text)
    if len(query) < 3:
        return []
    raw = None
    for attempt in range(2):                     # DuckDuckGo ara sıra boş/hata döner: bir kez daha dene
        try:
            from ddgs import DDGS
            raw = DDGS(timeout=settings.web_timeout).text(
                query, region=settings.web_region, max_results=settings.web_results)
            break
        except Exception as e:                   # ağ yok, engellendi, kota, sonuç yok...
            log.warning("internet araması başarısız (deneme %d): %s", attempt + 1, e)
            if attempt == 0:
                time.sleep(1.5)
    out = []
    for r in raw or []:
        url = str(r.get("href") or "")
        if url.startswith(("http://", "https://")):
            out.append({"title": str(r.get("title") or url).strip()[:200],
                        "snippet": str(r.get("body") or "").strip()[:400], "url": url})
    return out[:settings.web_results]
