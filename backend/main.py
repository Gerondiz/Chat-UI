import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import chat_db
import workspace_db
from mcp_host import mcp_host
from state import AppState, auto_select_models, default_config
from routes import chat, chat_history, collections, provider_routes, workspaces


logger = logging.getLogger(__name__)

app = FastAPI(title="Chat-UI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.on_event("startup")
async def startup():
    workspace_db.init_db()
    chat_db.init_db()
    cfg = default_config("ollama")
    state = AppState()
    provider = state.make_provider(cfg)
    cfg = await auto_select_models(provider, cfg)
    provider = state.make_provider(cfg)
    state.set(provider, cfg)
    app.state.state = state

    asyncio.create_task(mcp_host.start())
    ready = await mcp_host.wait_ready(timeout=20)
    if ready:
        logger.info("MCP host ready with tools: %s", [t.name for t in mcp_host.tools])
    else:
        logger.warning("MCP host not ready (timeout), agent mode will fall back to RAG")


app.include_router(provider_routes.router)
app.include_router(chat.router)
app.include_router(collections.router)
app.include_router(workspaces.router)
app.include_router(chat_history.router)
