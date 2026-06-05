import asyncio
import logging

from models import ProviderConfig
from providers.base import BaseProvider
from providers.ollama import OllamaProvider
from providers.openai import OpenAIProvider
from providers.lmstudio import LMStudioProvider


logger = logging.getLogger(__name__)


class AppState:
    def __init__(self):
        self._provider: BaseProvider | None = None
        self._config: ProviderConfig | None = None
        self._lock = asyncio.Lock()

    @property
    def provider(self) -> BaseProvider:
        assert self._provider is not None
        return self._provider

    @property
    def config(self) -> ProviderConfig:
        assert self._config is not None
        return self._config

    async def lock(self):
        await self._lock.acquire()

    def unlock(self):
        if self._lock.locked():
            self._lock.release()

    def set(self, provider: BaseProvider, config: ProviderConfig):
        self._provider = provider
        self._config = config

    @staticmethod
    def make_provider(cfg: ProviderConfig) -> BaseProvider:
        if cfg.name == "ollama":
            return OllamaProvider(
                base_url=cfg.base_url,
                chat_model=cfg.chat_model,
                embedding_model=cfg.embedding_model,
            )
        if cfg.name == "openai":
            return OpenAIProvider(
                base_url=cfg.base_url,
                chat_model=cfg.chat_model,
                embedding_model=cfg.embedding_model,
                api_key=cfg.api_key,
            )
        if cfg.name == "lmstudio":
            return LMStudioProvider(
                base_url=cfg.base_url,
                chat_model=cfg.chat_model,
                embedding_model=cfg.embedding_model,
                api_key=cfg.api_key,
            )
        raise ValueError(f"Unknown provider: {cfg.name}")


def default_config(name: str = "ollama") -> ProviderConfig:
    import config
    if name == "ollama":
        return ProviderConfig(
            name="ollama", chat_model="", embedding_model="",
            base_url=config.OLLAMA_BASE_URL,
        )
    if name == "openai":
        return ProviderConfig(
            name="openai", chat_model="", embedding_model="",
            base_url=config.OPENAI_BASE_URL,
            api_key=config.OPENAI_API_KEY,
        )
    return ProviderConfig(
        name="lmstudio", chat_model="", embedding_model="",
        base_url=config.LMSTUDIO_BASE_URL,
    )


async def auto_select_models(provider: BaseProvider, cfg: ProviderConfig) -> ProviderConfig:
    try:
        chat_models, embedding_models = await provider.list_models()
        if chat_models and not cfg.chat_model:
            cfg.chat_model = chat_models[0]
        if embedding_models and not cfg.embedding_model:
            cfg.embedding_model = embedding_models[0]
    except Exception:
        pass
    if not cfg.chat_model:
        cfg.chat_model = "gemma3:4b"
    if not cfg.embedding_model:
        cfg.embedding_model = "nomic-embed-text"
    return cfg
