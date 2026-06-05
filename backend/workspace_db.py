import json
import sqlite3
import threading
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "chatui.db"

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(str(DB_PATH))
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def init_db():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workspaces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            provider TEXT NOT NULL DEFAULT 'ollama',
            chat_model TEXT NOT NULL DEFAULT '',
            embedding_model TEXT NOT NULL DEFAULT '',
            system_prompt TEXT NOT NULL DEFAULT '',
            temperature REAL NOT NULL DEFAULT 0.7,
            max_tokens INTEGER NOT NULL DEFAULT 4096,
            top_p REAL NOT NULL DEFAULT 0.9,
            context_length INTEGER NOT NULL DEFAULT 8192,
            collections TEXT NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["collections"] = json.loads(d.get("collections", "[]"))
    return d


def list_workspaces() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM workspaces ORDER BY updated_at DESC").fetchall()
    return [_row_to_dict(r) for r in rows]


def create_workspace(data: dict) -> dict:
    conn = _get_conn()
    cols_str = json.dumps(data.get("collections", []), ensure_ascii=False)
    cur = conn.execute(
        """INSERT INTO workspaces (name, provider, chat_model, embedding_model,
           system_prompt, temperature, max_tokens, top_p, context_length, collections)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.get("name", "Новое пространство"),
            data.get("provider", "ollama"),
            data.get("chat_model", ""),
            data.get("embedding_model", ""),
            data.get("system_prompt", ""),
            data.get("temperature", 0.7),
            data.get("max_tokens", 4096),
            data.get("top_p", 0.9),
            data.get("context_length", 8192),
            cols_str,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _row_to_dict(row)


def get_workspace(ws_id: int) -> dict | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (ws_id,)).fetchone()
    return _row_to_dict(row) if row else None


def update_workspace(ws_id: int, data: dict) -> dict | None:
    conn = _get_conn()
    existing = conn.execute("SELECT * FROM workspaces WHERE id = ?", (ws_id,)).fetchone()
    if not existing:
        return None
    allowed = {"name", "provider", "chat_model", "embedding_model", "system_prompt",
               "temperature", "max_tokens", "top_p", "context_length", "collections"}
    updates = {}
    for k in allowed:
        if k in data:
            updates[k] = data[k]
    if not updates:
        return _row_to_dict(existing)
    if "collections" in updates:
        updates["collections"] = json.dumps(updates["collections"], ensure_ascii=False)
    set_items = [f"{k} = ?" for k in updates] + ["updated_at = datetime('now')"]
    set_clause = ", ".join(set_items)
    values = list(updates.values())
    conn.execute(f"UPDATE workspaces SET {set_clause} WHERE id = ?", (*values, ws_id))
    conn.commit()
    row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (ws_id,)).fetchone()
    return _row_to_dict(row)


def delete_workspace(ws_id: int) -> bool:
    conn = _get_conn()
    cur = conn.execute("DELETE FROM workspaces WHERE id = ?", (ws_id,))
    conn.commit()
    return cur.rowcount > 0
