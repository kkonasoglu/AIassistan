"""Bilgi bankası kayıtları (ChromaDB). Yönetim işlemleri: ekle, düzenle, sil, geri al, dışa aktar.

Her kayıt bir Chroma kaydıdır:
  document : "Başlık\\n\\nÇözüm"  (embedding bu metinden üretilir; düzenlenince yeniden üretilir)
  metadata : title, solution, author, created_at, updated_at, updated_by, deleted(bool)

Silme gerçek silme değildir: kayıt `deleted=True` olur, aramadan çıkar, admin "Geri al" diyebilir.
Yetki kontrolü API katmanında (require_admin) yapılır; bu servis kimin çağırdığını bilmez,
yalnızca kimin yaptığını kayda yazar.
"""
import threading
import uuid
from datetime import datetime, timezone

from app.services import rag
from app.services.intent import norm
from app.services.llm import embed

MAX_TITLE = 200
MAX_SOLUTION = 8000
_write_lock = threading.Lock()  # aynı anda iki yazma aynı başlıkla çift kayıt oluşturmasın


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean(title: str, solution: str) -> tuple[str, str]:
    title, solution = title.strip(), solution.strip()
    if not title or not solution:
        raise ValueError("Başlık ve çözüm boş olamaz.")
    if len(title) > MAX_TITLE:
        raise ValueError(f"Başlık en fazla {MAX_TITLE} karakter olabilir.")
    if len(solution) > MAX_SOLUTION:
        raise ValueError(f"Çözüm en fazla {MAX_SOLUTION} karakter olabilir.")
    return title, solution


def _record(record_id: str, meta: dict) -> dict:
    return {
        "id": record_id, "title": meta.get("title", ""), "solution": meta.get("solution", ""),
        "author": meta.get("author", ""), "created_at": meta.get("created_at", ""),
        "updated_at": meta.get("updated_at", ""), "updated_by": meta.get("updated_by", ""),
        "deleted": bool(meta.get("deleted", False)),
    }


def _meta(record_id: str) -> dict:
    got = rag.collection().get(ids=[record_id], include=["metadatas"])
    if not got["ids"]:
        raise ValueError("Kayıt bulunamadı.")
    return dict(got["metadatas"][0])


def list_all(include_deleted: bool = False) -> list[dict]:
    got = rag.collection().get(include=["metadatas"])
    records = [_record(i, m) for i, m in zip(got["ids"], got["metadatas"])]
    if not include_deleted:
        records = [r for r in records if not r["deleted"]]
    return sorted(records, key=lambda r: r["updated_at"], reverse=True)


def _ensure_unique_title(title: str, exclude_id: str | None = None) -> None:
    wanted = norm(" ".join(title.split()))
    for r in list_all():
        if r["id"] != exclude_id and norm(" ".join(r["title"].split())) == wanted:
            raise ValueError("Bu başlıkta bir kayıt zaten var. Mevcut kaydı düzenleyin.")


def title_exists(title: str) -> bool:
    try:
        _ensure_unique_title(title)
        return False
    except ValueError:
        return True


def add(title: str, solution: str, author: str) -> str:
    title, solution = _clean(title, solution)
    with _write_lock:
        _ensure_unique_title(title)
        text = f"{title}\n\n{solution}"
        now = _now()
        record_id = uuid.uuid4().hex
        rag.collection().add(
            ids=[record_id], documents=[text], embeddings=embed([text]),
            metadatas=[{"title": title, "solution": solution, "author": author,
                        "created_at": now, "updated_at": now, "updated_by": author,
                        "deleted": False}],
        )
    return record_id


def update(record_id: str, title: str, solution: str, editor: str) -> None:
    title, solution = _clean(title, solution)
    with _write_lock:
        meta = _meta(record_id)
        if not meta.get("deleted"):
            _ensure_unique_title(title, exclude_id=record_id)
        text = f"{title}\n\n{solution}"
        meta.update(title=title, solution=solution, updated_at=_now(), updated_by=editor)
        rag.collection().update(ids=[record_id], documents=[text],
                                embeddings=embed([text]), metadatas=[meta])


def delete(record_id: str, actor: str) -> None:
    """Gizler (geri alınabilir). Zaten gizliyse bir şey yapmaz."""
    with _write_lock:
        meta = _meta(record_id)
        meta.update(deleted=True, updated_at=_now(), updated_by=actor)
        rag.collection().update(ids=[record_id], metadatas=[meta])


def restore(record_id: str, actor: str) -> None:
    with _write_lock:
        meta = _meta(record_id)
        _ensure_unique_title(meta["title"], exclude_id=record_id)  # aynı başlıklı aktif kayıt var mı
        meta.update(deleted=False, updated_at=_now(), updated_by=actor)
        rag.collection().update(ids=[record_id], metadatas=[meta])


def export_all() -> dict:
    """Silinenler dahil tüm kayıtlar: yedek ve sunucuya taşıma için."""
    records = list_all(include_deleted=True)
    return {"exported_at": _now(), "count": len(records), "records": records}
