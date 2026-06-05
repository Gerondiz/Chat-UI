import os
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8001"))


class ChromaManager:
    def __init__(self) -> None:
        self._client: chromadb.ClientAPI | None = None

    def _get_client(self) -> chromadb.ClientAPI:
        if self._client is None:
            self._client = chromadb.HttpClient(
                host=CHROMA_HOST,
                port=CHROMA_PORT,
                settings=ChromaSettings(
                    allow_reset=True,
                    anonymized_telemetry=False,
                ),
            )
        return self._client

    def list_collections(self) -> list[dict[str, Any]]:
        client = self._get_client()
        try:
            collections = client.list_collections()
            result = []
            for c in collections:
                all_items = c.get(limit=10000)
                files: set[str] = set()
                for m in all_items.get("metadatas") or []:
                    if m and m.get("filename"):
                        files.add(m["filename"])
                result.append({"name": c.name, "count": len(files)})
            return result
        except Exception:
            return []

    def search_collection(
        self, collection_name: str, query: str, n_results: int = 5
    ) -> list[dict[str, Any]]:
        client = self._get_client()
        try:
            col = client.get_collection(collection_name)
        except Exception as exc:
            raise ValueError(f"Collection '{collection_name}' not found") from exc
        try:
            result = col.query(query_texts=[query], n_results=n_results)
        except Exception as exc:
            raise ValueError(f"Query failed: {exc}") from exc
        docs: list[dict[str, Any]] = []
        for i, doc in enumerate(result.get("documents", [[]])[0]):
            meta = (result.get("metadatas", [[]])[0] or [{}])[i] or {}
            docs.append({
                "content": doc,
                "filename": meta.get("filename", "unknown"),
                "chunk": meta.get("chunk", 0),
            })
        return docs

    def get_collection_documents(self, name: str) -> list[dict[str, Any]]:
        client = self._get_client()
        try:
            col = client.get_collection(name)
            result = col.get(limit=1000)
            docs = []
            seen: set[str] = set()
            for meta in result.get("metadatas") or []:
                if meta and "filename" in meta and meta["filename"] not in seen:
                    seen.add(meta["filename"])
                    docs.append({"filename": meta["filename"]})
            return docs
        except Exception:
            return []

    def add_document_to_collection(
        self, name: str, filename: str, chunks: list[str]
    ) -> dict[str, Any]:
        client = self._get_client()
        col = client.get_collection(name)
        ids = [f"{filename}_{i}" for i in range(len(chunks))]
        metadatas = [{"filename": filename, "chunk": i} for i in range(len(chunks))]
        col.add(ids=ids, documents=chunks, metadatas=metadatas)
        return {"status": "ok", "chunks": len(chunks)}

    def create_collection(self, name: str) -> dict[str, Any]:
        client = self._get_client()
        client.create_collection(name=name)
        return {"status": "ok", "name": name}

    def delete_collection(self, name: str) -> dict[str, Any]:
        client = self._get_client()
        client.delete_collection(name)
        return {"status": "ok", "name": name}
