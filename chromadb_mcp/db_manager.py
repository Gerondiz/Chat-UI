from __future__ import annotations

import os
import chromadb
from chromadb.config import Settings as ChromaSettings
from typing import Any


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
        except Exception:
            raise ValueError(f"Collection '{collection_name}' not found")

        try:
            result = col.query(query_texts=[query], n_results=n_results)
        except Exception as e:
            raise ValueError(f"Query failed: {e}")

        docs: list[dict[str, Any]] = []
        for i, doc in enumerate(result.get("documents", [[]])[0]):
            meta = (result.get("metadatas", [[]])[0] or [{}])[i] or {}
            docs.append({
                "content": doc,
                "filename": meta.get("filename", "unknown"),
                "chunk": meta.get("chunk", 0),
            })
        return docs
