"""Sohbet geçmişi (SQLite). Her sohbet bir kullanıcıya aittir.

Sahiplik kontrolü BURADA yapılır: başkasının sohbetine erişmeye çalışan NotFound
alır (var olup olmadığı bile sızdırılmaz).

Asistan mesajı iki parçalıdır: `content` (modelin kısa notu / düz cevap) ve `cards`
(bilgi bankasından birebir gösterilen kayıtlar: [{"title", "solution"}]).
"""
import json

from app.db.database import transaction

DEFAULT_TITLE = "Yeni sohbet"


class NotFound(Exception):
    """Sohbet yok ya da bu kullanıcıya ait değil."""


def _owned(conn, user_id: int, conv_id: int):
    row = conn.execute(
        "SELECT * FROM conversations WHERE id=? AND user_id=?", (conv_id, user_id)
    ).fetchone()
    if not row:
        raise NotFound("Sohbet bulunamadı.")
    return row


def _load(raw: str | None) -> list:
    return json.loads(raw) if raw else []


def create_conversation(user_id: int) -> int:
    with transaction() as conn:
        return conn.execute(
            "INSERT INTO conversations (user_id) VALUES (?)", (user_id,)
        ).lastrowid


def list_conversations(user_id: int, limit: int = 100) -> list[dict]:
    with transaction() as conn:
        rows = conn.execute(
            "SELECT id, title, updated_at FROM conversations WHERE user_id=? "
            "ORDER BY updated_at DESC, id DESC LIMIT ?", (user_id, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def get_messages(user_id: int, conv_id: int) -> list[dict]:
    with transaction() as conn:
        _owned(conn, user_id, conv_id)
        rows = conn.execute(
            "SELECT id, role, content, sources, cards, created_at FROM messages "
            "WHERE conversation_id=? ORDER BY id", (conv_id,)
        ).fetchall()
    return [{**dict(r), "sources": _load(r["sources"]), "cards": _load(r["cards"])} for r in rows]


def add_message(user_id: int, conv_id: int, role: str, content: str,
                sources: list[str] | None = None, cards: list[dict] | None = None) -> int:
    with transaction() as conn:
        conv = _owned(conn, user_id, conv_id)
        mid = conn.execute(
            "INSERT INTO messages (conversation_id, role, content, sources, cards) "
            "VALUES (?, ?, ?, ?, ?)",
            (conv_id, role, content,
             json.dumps(sources, ensure_ascii=False) if sources else None,
             json.dumps(cards, ensure_ascii=False) if cards else None),
        ).lastrowid
        conn.execute("UPDATE conversations SET updated_at=datetime('now') WHERE id=?", (conv_id,))
        if role == "user" and conv["title"] == DEFAULT_TITLE:  # ilk soru başlık olur
            one_line = " ".join(content.split())
            title = one_line[:50] + ("…" if len(one_line) > 50 else "")
            conn.execute("UPDATE conversations SET title=? WHERE id=?", (title, conv_id))
        return mid


def recent_messages(user_id: int, conv_id: int, limit: int) -> list[dict]:
    """Sohbetin son `limit` mesajı, eskiden yeniye sıralı."""
    with transaction() as conn:
        _owned(conn, user_id, conv_id)
        rows = conn.execute(
            "SELECT role, content, cards FROM messages WHERE conversation_id=? "
            "ORDER BY id DESC LIMIT ?", (conv_id, limit)
        ).fetchall()
    return [{"role": r["role"], "content": r["content"], "cards": _load(r["cards"])}
            for r in reversed(rows)]


def delete_conversation(user_id: int, conv_id: int) -> None:
    with transaction() as conn:
        _owned(conn, user_id, conv_id)
        conn.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
        conn.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
