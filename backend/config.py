import os

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://20.0.0.136:1234/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8001"))

DEFAULT_SYSTEM_PROMPT = os.getenv(
    "DEFAULT_SYSTEM_PROMPT",
    "Ты — полезный ассистент. Отвечай на русском языке."
)

DEFAULT_CHAT_MODEL = os.getenv("DEFAULT_CHAT_MODEL", "gemma3:4b")
DEFAULT_EMBEDDING_MODEL = os.getenv("DEFAULT_EMBEDDING_MODEL", "nomic-embed-text")
