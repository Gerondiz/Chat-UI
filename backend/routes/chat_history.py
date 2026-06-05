import logging

from fastapi import APIRouter, HTTPException

import chat_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat_history"])


@router.get("/api/chats")
async def list_chats():
    return {"chats": chat_db.list_chats()}


@router.post("/api/chats")
async def create_chat(data: dict):
    title = data.get("title", "Новый чат")
    workspace_id = data.get("workspace_id")
    chat = chat_db.create_chat(title, workspace_id)
    return chat


@router.get("/api/chats/{chat_id}")
async def get_chat(chat_id: int):
    chat = chat_db.get_chat(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@router.patch("/api/chats/{chat_id}")
async def rename_chat(chat_id: int, data: dict):
    title = data.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    chat = chat_db.rename_chat(chat_id, title)
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@router.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: int):
    ok = chat_db.delete_chat(chat_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"status": "ok"}


@router.get("/api/chats/{chat_id}/messages")
async def get_messages(chat_id: int):
    chat = chat_db.get_chat(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"messages": chat_db.get_messages(chat_id)}


@router.post("/api/chats/{chat_id}/messages")
async def save_messages(chat_id: int, data: dict):
    chat = chat_db.get_chat(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    messages = data.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="No messages provided")
    return {"messages": chat_db.save_messages(chat_id, messages)}


@router.put("/api/chats/{chat_id}/title")
async def update_chat_title(chat_id: int, data: dict):
    title = data.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    chat = chat_db.rename_chat(chat_id, title)
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat
