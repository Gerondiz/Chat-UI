import os
from dotenv import load_dotenv

load_dotenv()

DEFAULT_PROVIDER = os.getenv("DEFAULT_PROVIDER", "ollama")
PROVIDER_TIMEOUT = float(os.getenv("PROVIDER_TIMEOUT", "900"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:1234/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LMSTUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234")

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8001"))

DEFAULT_SYSTEM_PROMPT = os.getenv(
    "DEFAULT_SYSTEM_PROMPT",
    "Ты — полезный ассистент. Отвечай на русском языке."
)
