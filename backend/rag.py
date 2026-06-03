import os
import asyncio
import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.errors import ChromaError

from config import CHROMA_HOST, CHROMA_PORT


_client = None


def _make_client():
    global _client
    if _client is None:
        _client = chromadb.HttpClient(
            host=CHROMA_HOST,
            port=CHROMA_PORT,
            settings=ChromaSettings(
                allow_reset=True,
                anonymized_telemetry=False,
            ),
        )
    return _client


def _get_client():
    try:
        return _make_client()
    except Exception:
        return None


async def list_collections():
    client = await asyncio.to_thread(_get_client)
    if client is None:
        return []
    try:
        collections = await asyncio.to_thread(client.list_collections)
        result = []
        for c in collections:
            count = await asyncio.to_thread(c.count)
            result.append({"name": c.name, "count": count})
        return result
    except ChromaError:
        return []


async def search_collection(name: str, query: str, k: int = 5):
    client = await asyncio.to_thread(_get_client)
    if client is None:
        return []
    try:
        col = await asyncio.to_thread(client.get_collection, name)
        if col is None:
            return []
        result = await asyncio.to_thread(
            col.query, query_texts=[query], n_results=k
        )
        docs = []
        for i, doc in enumerate(result.get("documents", [[]])[0]):
            meta = (result.get("metadatas", [[]])[0] or [{}])[i] or {}
            docs.append({
                "content": doc,
                "filename": meta.get("filename", "unknown"),
                "chunk": meta.get("chunk", 0),
            })
        return docs
    except Exception:
        return []


async def create_collection(name: str):
    client = await asyncio.to_thread(_get_client)
    if client is None:
        return {"status": "error", "detail": "ChromaDB not available"}
    await asyncio.to_thread(client.create_collection, name=name)
    return {"status": "ok", "name": name}


async def delete_collection(name: str):
    client = await asyncio.to_thread(_get_client)
    if client is None:
        return {"status": "error", "detail": "ChromaDB not available"}
    await asyncio.to_thread(client.delete_collection, name)
    return {"status": "ok", "name": name}


async def get_collection_documents(name: str):
    client = await asyncio.to_thread(_get_client)
    if client is None:
        return []
    try:
        col = await asyncio.to_thread(client.get_collection, name)
        result = await asyncio.to_thread(col.get, limit=1000)
        docs = []
        seen = set()
        for meta in (result.get("metadatas") or []):
            if meta and "filename" in meta and meta["filename"] not in seen:
                seen.add(meta["filename"])
                docs.append({"filename": meta["filename"]})
        return docs
    except Exception:
        return []


async def add_document_to_collection(name: str, filename: str, chunks: list[str]):
    client = await asyncio.to_thread(_get_client)
    if client is None:
        return {"status": "error", "detail": "ChromaDB not available"}
    col = await asyncio.to_thread(client.get_collection, name)
    ids = [f"{filename}_{i}" for i in range(len(chunks))]
    metadatas = [{"filename": filename, "chunk": i} for i in range(len(chunks))]
    await asyncio.to_thread(col.add, ids=ids, documents=chunks, metadatas=metadatas)
    return {"status": "ok", "chunks": len(chunks)}
