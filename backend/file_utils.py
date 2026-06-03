import os
import tempfile
import fitz  # PyMuPDF
from docx import Document as DocxDocument


def extract_text_from_file(filepath: str) -> str:
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        return _extract_pdf(filepath)
    elif ext == ".docx":
        return _extract_docx(filepath)
    elif ext == ".txt":
        return _extract_txt(filepath)
    return ""


def _extract_pdf(filepath: str) -> str:
    text = ""
    with fitz.open(filepath) as doc:
        for page in doc:
            text += page.get_text() + "\n"
    return text


def _extract_docx(filepath: str) -> str:
    doc = DocxDocument(filepath)
    return "\n".join(p.text for p in doc.paragraphs)


def _extract_txt(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


async def save_upload(file) -> str:
    os.makedirs("/tmp/chat-ui-uploads", exist_ok=True)
    _, ext = os.path.splitext(file.filename or "upload.txt")
    tmp = tempfile.NamedTemporaryFile(
        dir="/tmp/chat-ui-uploads", suffix=ext, delete=False
    )
    content = await file.read()
    with open(tmp.name, "wb") as f:
        f.write(content)
    return tmp.name
