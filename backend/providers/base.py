from abc import ABC, abstractmethod


class BaseProvider(ABC):
    @abstractmethod
    async def chat(
        self, messages: list[dict], system_prompt: str = "",
        temperature: float = 0.7, max_tokens: int = 4096, top_p: float = 0.9,
        reasoning: bool = True,
    ) -> str:
        ...

    @abstractmethod
    async def chat_stream(
        self, messages: list[dict], system_prompt: str = "",
        temperature: float = 0.7, max_tokens: int = 4096, top_p: float = 0.9,
        reasoning: bool = True,
    ):
        ...

    @abstractmethod
    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        ...

    @abstractmethod
    async def list_models(self) -> tuple[list[str], list[str]]:
        ...

    @abstractmethod
    async def check(self) -> bool:
        ...
