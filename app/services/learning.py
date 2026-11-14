"""Sohbetten öğrenme: yetkilinin anlattığı dağınık bilgiyi "Başlık + adım adım çözüm"e çevirir.

Akış (chat.py yönetir):
  admin anlatır + "bunu kaydet" -> structure() -> onay taslağı (drafts tablosu)
  admin "evet/kaydet" -> knowledge.add()      admin "iptal" -> taslak silinir

structure() iki katmanlıdır:
  1. Model metni YENİDEN YAZMAZ, yalnızca BÖLER: metni aynen tekrar yazıp bölümlerin arasına
     "|" koyar (ilk bölüm sorun/başlık, sonrakiler adım). Çıktıdan "|" çıkarılınca özgün
     metin AYNEN elde ediliyorsa kabul edilir. Böylece tek bir kelime eklenmemiş ya da
     atılmamıştır: uydurma yapısal olarak imkânsızdır. (Denendi: serbest yeniden yazdırınca
     3B model adım uydurdu; "metinden parça kopyala" denince de yeniden yazıp bilgi attı.)
  2. Doğrulama başarısızsa (veya model çalışmıyorsa) kural tabanlı düzenleme kullanılır.
Ayrıca kullanıcıya her zaman önizleme gösterilir; onaysız hiçbir şey kaydedilmez.
"""
import re

from app.db.database import transaction
from app.services import llm
from app.services.intent import norm

MAX_CONTENT = 3000
MIN_WORDS = 5
MAX_STEPS = 15
# Hata kodu: BÜYÜK harfli (KNK-204, KNK 204, KNK204) ya da tireli (knk-204).
# Küçük harfli + boşluk KOD DEĞİLDİR: "kontrol et 10 veya 11" -> "ET-10", "VEYA-11" olmasın.
_STRICT_CODE = re.compile(
    r"\b([A-ZÇĞİÖŞÜ]{2,6})\s*-?\s*(\d{2,5})\b|\b([A-Za-zÇĞİÖŞÜçğıöşü]{2,6})-(\d{2,5})\b")
_CONNECTORS = re.compile(
    r"\s*,?\s*\b(?:daha\s+sonra|ardından|sonrasında|sonra|en\s+son|son\s+olarak)\b\s*,?\s*",
    re.IGNORECASE)

STRUCT_PROMPT = (
    "Bir ofis destek uzmanı bir sorunu ve çözümünü dağınık şekilde anlattı. Senin görevin "
    "SADECE metni bölümlere ayırmak. Metni AYNEN, hiçbir kelimesini değiştirmeden, eklemeden "
    "veya çıkarmadan tekrar yaz ve bölümlerin arasına | işareti koy. İlk bölüm sorunu "
    "anlatan kısım olsun (hata kodu varsa o da orada), sonraki her bölüm tek bir çözüm adımı "
    "olsun. Başka hiçbir şey yazma.\n\n"
    "Örnek:\n"
    "Metin: bilgisayar açılmıyor önce fişi kontrol et sonra güç düğmesine uzun bas\n"
    "Cevap: bilgisayar açılmıyor | önce fişi kontrol et | sonra güç düğmesine uzun bas"
)


# ---------------- Taslak (onay bekleyen kayıt) ----------------
def save_draft(user_id: int, conv_id: int, title: str, solution: str) -> None:
    with transaction() as conn:
        conn.execute(
            "INSERT INTO drafts (conversation_id, user_id, title, solution) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(conversation_id) DO UPDATE SET user_id=excluded.user_id, "
            "title=excluded.title, solution=excluded.solution, created_at=datetime('now')",
            (conv_id, user_id, title, solution))


def get_draft(user_id: int, conv_id: int) -> dict | None:
    with transaction() as conn:
        row = conn.execute("SELECT title, solution FROM drafts WHERE conversation_id=? AND user_id=?",
                           (conv_id, user_id)).fetchone()
    return dict(row) if row else None


def clear_draft(conv_id: int) -> None:
    with transaction() as conn:
        conn.execute("DELETE FROM drafts WHERE conversation_id=?", (conv_id,))


# ---------------- Düzenleme ----------------
def format_solution(steps: list[str]) -> str:
    return "Çözüm adımları:\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))


def _code_matches(text: str) -> list[tuple[tuple[int, int], str]]:
    out = []
    for m in _STRICT_CODE.finditer(text):
        letters, digits = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        out.append((m.span(), f"{letters.upper()}-{digits}"))
    return out


def _codes(text: str) -> set[str]:
    return {code for _, code in _code_matches(text)}


def _tidy(s: str) -> str:
    return " ".join(s.split()).strip(" :,-.")


def _sentence_case(s: str) -> str:
    s = s.strip(" .,;:-")
    if not s:
        return s
    first = "İ" if s[0] == "i" else s[0].upper()   # Türkçe: i -> İ
    return first + s[1:]


def _strip_code(text: str, span: tuple[int, int]) -> str:
    """Kodu metinden çıkarır, "hata/hatası" kelimesini de atar: "KNK-500 hatası yazıcı" -> "yazıcı"."""
    rest = text[:span[0]] + " " + text[span[1]:]
    return _tidy(re.sub(r"\bhata(sı|sında|sını|sı ile)?\b", "", rest, flags=re.IGNORECASE))


def normalize_title(title: str) -> str:
    """Hata kodu varsa başlığı "KOD: açıklama" biçimine getirir ("Yazıcı KNK-500 Hatası" ->
    "KNK-500: Yazıcı"). Zaten "KOD: ..." veya "KOD - ..." ise dokunmaz."""
    title = _tidy(title)
    matches = _code_matches(title)
    if not matches:
        return _sentence_case(title)[:200]
    span, code = matches[0]
    if span[0] == 0 and re.match(r"^\s*[:\-–]", title[span[1]:]):   # zaten "KOD: ..." / "KOD - ..."
        return title[:200]
    rest = _strip_code(title, span)
    return (f"{code}: {_sentence_case(rest)}" if rest else code)[:200]


_ABLATIVE_END = re.compile(r"[dt][ae]n\s*,?\s*$", re.IGNORECASE)   # "doğruladıktan", "bittikten"


def _split_sequence(text: str) -> list[str]:
    """Metni "sonra / ardından / en son" gibi sıralama bağlaçlarından böler.
    "doğruladıktan sonra" gibi ZAMAN bildiren kullanımlar adım ayracı sayılmaz."""
    parts, start = [], 0
    for m in _CONNECTORS.finditer(text):
        before = text[start:m.start()]
        is_plain_sonra = m.group(0).strip(" ,").lower() == "sonra"
        if is_plain_sonra and _ABLATIVE_END.search(before):
            continue
        parts.append(before)
        start = m.end()
    parts.append(text[start:])
    return [p for p in parts if p.strip()]


def _prepare(content: str) -> str:
    """Satır yapısını korur; adım numaralarını ("1. ", satır başı veya aralarda) satır sonuna çevirir."""
    lines = [" ".join(line.split()) for line in content.splitlines() if line.strip()]
    text = "\n".join(lines)
    text = re.sub(r"(?<=\S)\s+\d{1,2}[.)]\s+(?=[A-Za-zÇĞİÖŞÜçğıöşü])", "\n", text)  # "x 2. y" -> satır
    return re.sub(r"(?m)^\s*\d{1,2}[.)]\s*", "", text)                              # satır başı "1. "


def _flat(text: str) -> str:
    """Karşılaştırma için: küçük harf, noktalama ve fazla boşluklar yok."""
    return " ".join(re.sub(r"[^\w\s]", " ", norm(text)).split())


_LEADING_CONNECTOR = re.compile(r"^\s*(?:önce|sonra|ardından|daha\s+sonra|en\s+son|son\s+olarak)\b\s*,?\s*",
                                re.IGNORECASE)
_CONNECTOR_WORDS = re.compile(
    r"\b(?:önce|sonra|ardından|sonrasında|daha\s+sonra|en\s+son|son\s+olarak)\b")
_LABEL = re.compile(r"^\s*(?:cevap|metin)\s*:\s*", re.IGNORECASE)


def _core(text: str) -> str:
    """Karşılaştırma özü: küçük harf, noktalama yok, "önce/sonra" gibi sıralama bağlaçları yok."""
    return " ".join(_CONNECTOR_WORDS.sub(" ", _flat(text)).split())


def _validate_ai(raw: str, source: str) -> tuple[str, list[str]] | None:
    """Model yalnızca BÖLME noktası ("|") eklediyse kabul edilir: çıktıdan "|" çıkarılınca özgün
    metnin aynısı elde edilmeli. Tek kelime eklenmişse, atılmışsa ya da değiştirilmişse
    reddedilir (sıralama bağlaçları hariç)."""
    parts = [p.strip(" \n\"'`") for p in _LABEL.sub("", raw).split("|")]
    parts = [p for p in parts if _flat(p)]
    if len(parts) < 2 or len(parts) > MAX_STEPS + 1:
        return None
    if _core(" ".join(parts)) != _core(source):
        return None
    title, steps = parts[0], parts[1:]
    clean = []
    for step in steps:
        for piece in _split_sequence(step):     # model bir adıma iki adım sıkıştırdıysa ayır
            piece = _LEADING_CONNECTOR.sub("", piece.strip())
            if _flat(piece):
                clean.append(_sentence_case(piece) + ".")
    title = _LEADING_CONNECTOR.sub("", title.strip())
    if not clean or not _flat(title) or len(title) > 200:
        return None
    codes = [c for _, c in _code_matches(source)]
    if codes and codes[0] not in _codes(title):     # model kodu başlığa almamış
        title = f"{codes[0]}: {_sentence_case(title)}"
    return normalize_title(title), clean


def basic_structure(content: str) -> tuple[str, list[str]]:
    """Model kullanmadan düzenleme: cümleleri ve "sonra / ardından" bağlaçlarını ayırır.
    İlk parça başlık olur, kalanlar numaralı adımlar. Hata kodu başlığın başına alınır."""
    text = _prepare(content)
    parts: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        for seg in _split_sequence(sentence):
            seg = re.sub(r"^\s*önce\b\s*,?\s*", "", seg.strip(), flags=re.IGNORECASE).strip(" .,;:-")
            if seg:
                parts.append(seg)
    if not parts:
        return "Yeni kayıt", [" ".join(content.split())]
    head, rest = parts[0], parts[1:]
    in_head = _code_matches(head)
    if in_head:
        span, code = in_head[0]
        problem = _strip_code(head, span)
    else:
        found = _code_matches(text)
        code, problem = (found[0][1] if found else None), _tidy(head)
    title = f"{code}: {_sentence_case(problem)}" if code and problem else (code or _sentence_case(head))
    steps = [_sentence_case(p) + "." for p in rest] or [_sentence_case(head) + "."]
    return title[:200], steps[:MAX_STEPS]


def structure(content: str) -> dict:
    """Dağınık anlatımı {"title", "solution", "by"} haline getirir. by: "ai" | "basic"."""
    content = "\n".join(" ".join(l.split()) for l in content.splitlines() if l.strip())[:MAX_CONTENT]
    try:
        ai = _validate_ai(llm.complete_text(STRUCT_PROMPT, "Metin: " + content), content)
    except Exception:  # Ollama kapalı, zaman aşımı vb. -> kural tabanlıya düş
        ai = None
    if ai:
        title, steps = ai
        return {"title": title, "solution": format_solution(steps), "by": "ai"}
    title, steps = basic_structure(content)
    return {"title": title, "solution": format_solution(steps), "by": "basic"}
