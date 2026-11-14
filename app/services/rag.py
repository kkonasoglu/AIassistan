"""Bilgi bankası arama servisi (ChromaDB).

Kayıt yapısı (her kayıt bir Chroma kaydı):
  document : "Başlık\\n\\nÇözüm adımları"  (embedding bu metinden üretilir)
  metadata : title, solution, author, created_at, updated_at, deleted(bool)
Silinen kayıtlar gerçekten silinmez, deleted=True olur ve aramada elenir.

Arama iki yoldan yapılır:
  1. Hata kodu (KNK-204 gibi) geçiyorsa BİREBİR eşleşme: embedding modelleri kodları
     iyi ayırt edemez ("KNK-310 nedir" sorusunda doğru kayıt birinci çıkmıyordu).
  2. Aksi halde anlamsal arama: soru -> embedding -> en yakın kayıtlar.
"""
import re

import chromadb

from app.core.config import settings
from app.services.llm import embed

_collection = None
_CODE_RE = re.compile(r"\b([A-Za-z]{2,6})\s*-?\s*(\d{2,5})\b")  # KNK-204, knk204, "knk 204", "KNK - 204"


def collection():
    global _collection
    if _collection is None:
        settings.vectorstore_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(settings.vectorstore_dir))
        _collection = client.get_or_create_collection(
            "knowledge", metadata={"hnsw:space": "cosine"}
        )
    return _collection


def reset_cache() -> None:
    """Testlerde veri klasörü değişince bağlantıyı sıfırlamak için."""
    global _collection
    _collection = None


def count() -> int:
    """Aktif (silinmemiş) kayıt sayısı."""
    return len(collection().get(where={"deleted": False}, include=[])["ids"])


def _hit(text: str, meta: dict, distance: float, **extra) -> dict:
    """Arama sonucu: kartta gösterilecek başlık + çözüm, modele giden birleşik metin."""
    solution = meta.get("solution") or text.split("\n\n", 1)[-1]
    return {"text": text, "title": meta.get("title", "kayıt"), "solution": solution,
            "distance": distance, **extra}


def _code_hits(query: str) -> list[dict]:
    codes = {f"{letters.upper()}-{digits}" for letters, digits in _CODE_RE.findall(query)}
    found = []
    for code in sorted(codes):
        got = collection().get(
            where={"deleted": False}, where_document={"$contains": code},
            include=["documents", "metadatas"],
        )
        for text, meta in zip(got["documents"], got["metadatas"]):
            found.append(_hit(text, meta, 0.0, code=code))
    # Kod başka bir kaydın metninde sadece geçiyor olabilir; başlığında geçenleri tercih et
    in_title = [h for h in found if h["code"] in h["title"].upper()]
    return in_title or found


def _semantic(query: str, k: int) -> list[dict]:
    """Eşik uygulanmamış anlamsal sonuçlar, yakından uzağa sıralı."""
    res = collection().query(
        query_embeddings=embed([query]),
        n_results=k,
        where={"deleted": False},
        include=["documents", "metadatas", "distances"],
    )
    return [_hit(t, m, d) for t, m, d in
            zip(res["documents"][0], res["metadatas"][0], res["distances"][0])]


def _select(hits: list[dict]) -> list[dict]:
    """Eşikleri uygular: çok uzak olanları at, en iyiden çok uzak olanları (gürültü) at.
    Gürültü modeli şaşırtır, istemi uzatır ve yanlış "kaynak" gösterir."""
    hits = [h for h in hits if h["distance"] <= settings.max_distance]
    if hits:
        best = hits[0]["distance"]
        hits = [h for h in hits if h["distance"] <= best + settings.source_margin]
    return hits


def search(query: str, k: int | None = None) -> list[dict]:
    """Soruya en yakın kayıtlar. Çok uzak (alakasız) ve silinmiş olanlar elenir."""
    if collection().count() == 0:
        return []
    by_code = _code_hits(query)
    if by_code:
        return by_code[: k or settings.top_k]
    return _select(_semantic(query, k or settings.top_k))


def debug_search(query: str, k: int = 6) -> dict:
    """Admin "arama testi": hangi kayıtlar hangi mesafeyle bulundu, hangisi kullanılırdı?
    Eşikleri gerçek verilerle ayarlamak için."""
    if collection().count() == 0:
        return {"mode": "empty", "rows": []}
    by_code = _code_hits(query)
    if by_code:
        return {"mode": "code", "rows": [
            {"title": h["title"], "distance": 0.0, "used": True} for h in by_code[: settings.top_k]]}
    hits = _semantic(query, k)
    used = {h["title"] for h in _select(hits[: settings.top_k])}
    return {"mode": "semantic", "max_distance": settings.max_distance,
            "source_margin": settings.source_margin,
            "rows": [{"title": h["title"], "distance": round(h["distance"], 3),
                      "used": h["title"] in used} for h in hits]}


def build_note_message(question: str, hits: list[dict]) -> str:
    """Modelin kısa not yazması için: bulunan kayıt(lar) + kullanıcının mesajı."""
    records = "\n\n".join(h["text"] for h in hits)
    return (f"BULUNAN KAYIT:\n{records}\n\nKULLANICININ MESAJI: {question}\n"
            f"{settings.lang_reminder}")
