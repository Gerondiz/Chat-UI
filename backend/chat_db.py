import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "chatui.db"

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn


def init_db():
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT 'Новый чат',
            workspace_id INTEGER REFERENCES workspaces(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
            client_id TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            thinking TEXT NOT NULL DEFAULT '',
            metrics TEXT NOT NULL DEFAULT '{}',
            sources TEXT NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def list_chats() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute("""
        SELECT c.*, COUNT(m.id) AS message_count
        FROM chats c
        LEFT JOIN chat_messages m ON m.chat_id = c.id
        GROUP BY c.id
        ORDER BY c.updated_at DESC
    """).fetchall()
    return [_row_to_dict(r) for r in rows]


def create_chat(title: str = "Новый чат", workspace_id: int | None = None) -> dict:
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO chats (title, workspace_id) VALUES (?, ?)",
        (title, workspace_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM chats WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _row_to_dict(row)


def get_chat(chat_id: int) -> dict | None:
    conn = _get_conn()
    row = conn.execute("""
        SELECT c.*, COUNT(m.id) AS message_count
        FROM chats c
        LEFT JOIN chat_messages m ON m.chat_id = c.id
        WHERE c.id = ?
        GROUP BY c.id
    """, (chat_id,)).fetchone()
    return _row_to_dict(row) if row else None


def rename_chat(chat_id: int, title: str) -> dict | None:
    conn = _get_conn()
    conn.execute(
        "UPDATE chats SET title = ?, updated_at = datetime('now') WHERE id = ?",
        (title, chat_id),
    )
    conn.commit()
    return get_chat(chat_id)


def delete_chat(chat_id: int) -> bool:
    conn = _get_conn()
    cur = conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
    conn.commit()
    return cur.rowcount > 0


def get_messages(chat_id: int) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM chat_messages WHERE chat_id = ? ORDER BY id ASC",
        (chat_id,),
    ).fetchall()
    result = []
    for r in rows:
        d = _row_to_dict(r)
        d["metrics"] = json.loads(d.get("metrics", "{}"))
        d["sources"] = json.loads(d.get("sources", "[]"))
        # Only return fields needed by frontend Message type
        result.append({
            "id": d["id"],
            "client_id": d["client_id"],
            "role": d["role"],
            "content": d["content"],
            "thinking": d["thinking"] or None,
            "metrics": d["metrics"] or None,
            "sources": d["sources"],
            "ts": int(datetime.strptime(d["created_at"], "%Y-%m-%d %H:%M:%S").timestamp() * 1000) if d.get("created_at") else 0,
        })
    return result


def save_messages(chat_id: int, messages: list[dict]) -> list[dict]:
    conn = _get_conn()
    for msg in messages:
        metrics = json.dumps(msg.get("metrics") or {}, ensure_ascii=False)
        sources = json.dumps(msg.get("sources") or [], ensure_ascii=False)
        conn.execute(
            """INSERT INTO chat_messages (chat_id, client_id, role, content, thinking, metrics, sources)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                chat_id,
                msg.get("id", ""),
                msg["role"],
                msg.get("content", ""),
                msg.get("thinking", ""),
                metrics,
                sources,
            ),
        )
    conn.execute(
        "UPDATE chats SET updated_at = datetime('now') WHERE id = ?",
        (chat_id,),
    )
    conn.commit()
    return get_messages(chat_id)
