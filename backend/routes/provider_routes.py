import logging

from fastapi import APIRouter, Request

from models import ProviderConfig, ProviderSwitch
from state import AppState, auto_select_models, default_config


logger = logging.getLogger(__name__)

router = APIRouter(tags=["provider"])


def _get_state(request: Request) -> AppState:
    return request.app.state.state


@router.get("/api/providers")
async def get_providers():
    return {"providers": ["ollama", "openai", "lmstudio"]}


@router.get("/api/provider")
async def get_provider(request: Request):
    state = _get_state(request)
    async with state._lock:
        return state.config


@router.put("/api/provider")
async def switch_provider(switch: ProviderSwitch, request: Request):
    state = _get_state(request)
    async with state._lock:
        cfg = default_config(switch.name)
        provider = state.make_provider(cfg)
        cfg = await auto_select_models(provider, cfg)
        provider = state.make_provider(cfg)
        state.set(provider, cfg)
    return state.config


@router.put("/api/provider/config")
async def update_provider_config(cfg: ProviderConfig, request: Request):
    state = _get_state(request)
    async with state._lock:
        provider = state.make_provider(cfg)
        state.set(provider, cfg)
    return state.config


@router.get("/api/provider/status")
async def provider_status(request: Request):
    state = _get_state(request)
    async with state._lock:
        try:
            online = await state.provider.check()
            chat_models, embedding_models = [], []
            if online:
                chat_models, embedding_models = await state.provider.list_models()
            return {
                "name": state.config.name,
                "online": online,
                "chat_model": state.config.chat_model,
                "embedding_model": state.config.embedding_model,
                "chat_models": chat_models,
                "embedding_models": embedding_models,
            }
        except Exception as e:
            return {
                "name": state.config.name,
                "online": False,
                "chat_model": state.config.chat_model,
                "embedding_model": state.config.embedding_model,
                "chat_models": [],
                "embedding_models": [],
                "error": str(e),
            }


@router.get("/api/provider/models")
async def provider_models(request: Request):
    state = _get_state(request)
    async with state._lock:
        chat_models, embedding_models = await state.provider.list_models()
    return {"chat_models": chat_models, "embedding_models": embedding_models}
