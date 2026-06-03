from pydantic import BaseModel


class Message(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]
    system_prompt: str = ""
    mode: str = "chat"  # "chat" | "rag"
    collection: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 0.9
    stream: bool = False
    reasoning: bool = True


class ProviderConfig(BaseModel):
    name: str
    chat_model: str
    embedding_model: str
    base_url: str
    api_key: str = ""


class ProviderSwitch(BaseModel):
    name: str  # "ollama" | "openai"


class ProviderModels(BaseModel):
    chat_models: list[str]
    embedding_models: list[str]


class ProviderStatus(BaseModel):
    name: str
    online: bool
    chat_model: str
    embedding_model: str
    chat_models: list[str] = []
    embedding_models: list[str] = []
    error: str = ""
