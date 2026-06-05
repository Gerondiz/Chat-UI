import logging

from fastapi import APIRouter, HTTPException, UploadFile, File

import rag
from file_utils import extract_text_from_file, chunk_text, save_upload


logger = logging.getLogger(__name__)

router = APIRouter(tags=["collections"])


@router.get("/api/collections")
async def get_collections():
    try:
        cols = await rag.list_collections()
        return {"collections": cols}
    except Exception as e:
        return {"collections": [], "error": str(e)}


@router.post("/api/collections")
async def create_collection(name: str):
    try:
        return await rag.create_collection(name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/collections/{name}")
async def delete_collection(name: str):
    try:
        return await rag.delete_collection(name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/collections/{name}/documents")
async def get_documents(name: str):
    try:
        docs = await rag.get_collection_documents(name)
        return {"documents": docs}
    except Exception as e:
        return {"documents": [], "error": str(e)}


@router.post("/api/collections/{name}/documents")
async def upload_document(name: str, file: UploadFile = File(...)):
    try:
        filepath = await save_upload(file)
        text = extract_text_from_file(filepath)
        if not text.strip():
            raise HTTPException(status_code=400, detail="Не удалось извлечь текст из файла")
        chunks = chunk_text(text)
        result = await rag.add_document_to_collection(
            name, file.filename or "document", chunks
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
