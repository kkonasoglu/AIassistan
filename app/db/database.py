"""SQLite altyapısı.

Her işlem tek bir "transaction" içinde yapılır: ya hepsi uygulanır ya hiçbiri.
Bu, "en az 1 admin kalmalı" gibi kuralların yarım kalmasını engeller.
"""
import sqlite3
from contextlib import contextmanager

from app.core.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'user')),
    is_active     INTEGER NOT NULL DEFAULT 1,
    display_name  TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    title      TEXT NOT NULL DEFAULT 'Yeni sohbet',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    sources         TEXT,
    cards           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Onay bekleyen "öğrenme" taslağı: sohbet başına en fazla bir tane
CREATE TABLE IF NOT EXISTS drafts (
    conversation_id INTEGER PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    title           TEXT NOT NULL,
    solution        TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);
CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id, updated_at);
"""


@contextmanager
def transaction():
    """BEGIN IMMEDIATE: yazma kilidini baştan alır, böylece kontrol ile
    güncelleme arasında başka işlem araya giremez."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def init_db() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    # WAL modu: birden çok kullanıcı aynı anda okurken biri yazabilir.
    # Transaction dışında ayarlanır; dosyaya kalıcı olarak işlenir.
    boot = sqlite3.connect(settings.db_path)
    boot.execute("PRAGMA journal_mode=WAL")
    boot.close()
    with transaction() as conn:
        for statement in SCHEMA.split(";"):
            if statement.strip():
                conn.execute(statement)
        # Eski veritabanlarına sonradan eklenen sütunlar (CREATE TABLE IF NOT EXISTS
        # var olan tabloyu değiştirmez)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(messages)")}
        ucols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        if "display_name" not in ucols:
            conn.execute("ALTER TABLE users ADD COLUMN display_name TEXT NOT NULL DEFAULT ''")
        if "cards" not in cols:
            conn.execute("ALTER TABLE messages ADD COLUMN cards TEXT")
