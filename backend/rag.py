import asyncio

from chroma_client import ChromaManager

_db = ChromaManager()


async def list_collections():
    return await asyncio.to_thread(_db.list_collections)


async def search_collection(name: str, query: str, k: int = 5):
    try:
        return await asyncio.to_thread(_db.search_collection, name, query, k)
    except ValueError:
        return []


async def create_collection(name: str):
    try:
        return await asyncio.to_thread(_db.create_collection, name)
    except Exception as e:
        return {"status": "error", "detail": str(e)}


async def delete_collection(name: str):
    try:
        return await asyncio.to_thread(_db.delete_collection, name)
    except Exception as e:
        return {"status": "error", "detail": str(e)}


async def get_collection_documents(name: str):
    return await asyncio.to_thread(_db.get_collection_documents, name)


async def add_document_to_collection(name: str, filename: str, chunks: list[str]):
    return await asyncio.to_thread(_db.add_document_to_collection, name, filename, chunks)
