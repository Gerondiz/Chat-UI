import json
import logging
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import config
from models import ChatRequest, ProviderConfig, ProviderSwitch
from providers.base import BaseProvider, ToolCall
from providers.ollama import OllamaProvider
from providers.openai import OpenAIProvider
from providers.lmstudio import LMStudioProvider
from mcp_host import mcp_host, run_mcp_host
import rag
from file_utils import extract_text_from_file, chunk_text, save_upload

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

# --- Provider management ---

current_provider: BaseProvider = None
current_config: ProviderConfig = None


def _make_provider(cfg: ProviderConfig) -> BaseProvider:
    if cfg.name == "ollama":
        return OllamaProvider(
            base_url=cfg.base_url,
            chat_model=cfg.chat_model,
            embedding_model=cfg.embedding_model,
        )
    elif cfg.name == "openai":
        return OpenAIProvider(
            base_url=cfg.base_url,
            chat_model=cfg.chat_model,
            embedding_model=cfg.embedding_model,
            api_key=cfg.api_key,
        )
    elif cfg.name == "lmstudio":
        return LMStudioProvider(
            base_url=cfg.base_url,
            chat_model=cfg.chat_model,
            embedding_model=cfg.embedding_model,
            api_key=cfg.api_key,
        )
    raise ValueError(f"Unknown provider: {cfg.name}")


def _default_config(name: str = "ollama") -> ProviderConfig:
    if name == "ollama":
        return ProviderConfig(
            name="ollama",
            chat_model=config.DEFAULT_CHAT_MODEL,
            embedding_model=config.DEFAULT_EMBEDDING_MODEL,
            base_url=config.OLLAMA_BASE_URL,
        )
    if name == "openai":
        return ProviderConfig(
            name="openai",
            chat_model="google/gemma-4-e4b",
            embedding_model="text-embedding-nomic-embed-text-v1.5",
            base_url=config.OPENAI_BASE_URL,
            api_key=config.OPENAI_API_KEY,
        )
    return ProviderConfig(
        name="lmstudio",
        chat_model="google/gemma-4-e4b",
        embedding_model="text-embedding-nomic-embed-text-v1.5",
        base_url=config.OPENAI_BASE_URL,
        api_key=config.OPENAI_API_KEY,
    )


@app.on_event("startup")
async def startup():
    global current_provider, current_config
    current_config = _default_config("ollama")
    current_provider = _make_provider(current_config)
    # start MCP host in background
    import asyncio
    asyncio.create_task(mcp_host.start())
    ready = await mcp_host.wait_ready(timeout=5)
    if ready:
        logger.info("MCP host ready with tools: %s", [t.name for t in mcp_host.tools])
    else:
        logger.warning("MCP host not ready (timeout), agent mode will fall back to RAG")


# --- Provider endpoints ---

@app.get("/api/providers")
async def get_providers():
    return {"providers": ["ollama", "openai", "lmstudio"]}


@app.get("/api/provider")
async def get_provider():
    return current_config


@app.put("/api/provider")
async def switch_provider(switch: ProviderSwitch):
    global current_provider, current_config
    current_config = _default_config(switch.name)
    current_provider = _make_provider(current_config)
    return current_config


@app.put("/api/provider/config")
async def update_provider_config(cfg: ProviderConfig):
    global current_provider, current_config
    current_config = cfg
    current_provider = _make_provider(cfg)
    return current_config


@app.get("/api/provider/status")
async def provider_status():
    global current_provider, current_config
    try:
        online = await current_provider.check()
        chat_models, embedding_models = [], []
        if online:
            chat_models, embedding_models = await current_provider.list_models()
        return {
            "name": current_config.name,
            "online": online,
            "chat_model": current_config.chat_model,
            "embedding_model": current_config.embedding_model,
            "chat_models": chat_models,
            "embedding_models": embedding_models,
        }
    except Exception as e:
        return {
            "name": current_config.name,
            "online": False,
            "chat_model": current_config.chat_model,
            "embedding_model": current_config.embedding_model,
            "chat_models": [],
            "embedding_models": [],
            "error": str(e),
        }


@app.get("/api/provider/models")
async def provider_models():
    chat_models, embedding_models = await current_provider.list_models()
    return {"chat_models": chat_models, "embedding_models": embedding_models}


# --- Chat endpoints ---

def _build_messages(req: ChatRequest) -> list[dict]:
    msgs = [m.model_dump() for m in req.messages]
    if req.system_prompt:
        msgs.insert(0, {"role": "system", "content": req.system_prompt})
    return msgs


def _extract_thinking(resp: str) -> tuple[str, str]:
    """Split response into (content, thinking) based on <think> tags."""
    if "<think" in resp and "</think>" in resp:
        t_start = resp.index("<think")
        t_end = resp.index("</think>") + len("</think>")
        thinking = resp[t_start:t_end]
        content = resp[:t_start] + resp[t_end:]
        return content, thinking
    return resp, ""


async def _run_agent_loop(
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    top_p: float,
    reasoning: bool,
    max_iterations: int = 5,
) -> tuple[str, list[dict]]:
    """Run the agent tool-calling loop. Returns (final_content, all_sources)."""
    all_sources: list[dict] = []
    current_messages = list(messages)
    tool_schemas = mcp_host.get_tool_schemas()

    for iteration in range(max_iterations):
        result = await current_provider.chat_with_tools(
            current_messages,
            system_prompt="",
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            reasoning=reasoning,
            tools=tool_schemas,
        )

        # Append assistant response to conversation
        assistant_msg: dict = {"role": "assistant", "content": result.content}
        if result.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments) if isinstance(tc.arguments, dict) else tc.arguments,
                    }
                }
                for tc in result.tool_calls
            ]
        current_messages.append(assistant_msg)

        if not result.tool_calls:
            # No tools called — final response
            return result.content, all_sources

        # Execute tool calls
        text_results: list[str] = []
        for tc in result.tool_calls:
            try:
                mcp_results = await mcp_host.call_tool(tc.name, tc.arguments)
                text = "\n".join(r.text for r in mcp_results)
                text_results.append(text or "No results")
                # Collect sources from search_chromadb results
                if tc.name == "search_chromadb":
                    for r in mcp_results:
                        all_sources.append({"content": r.text[:200], "filename": tc.arguments.get("collection_name", "unknown")})
            except Exception as exc:
                text_results.append(f"Error executing tool '{tc.name}': {exc}")
                logger.error("Tool call failed: %s(%s) — %s", tc.name, tc.arguments, exc)

        # Append tool results to conversation
        tool_messages = current_provider.format_tool_messages(result.tool_calls, text_results)
        current_messages.extend(tool_messages)

    # Max iterations reached — force direct response
    final = await current_provider.chat(
        current_messages,
        system_prompt="",
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        reasoning=reasoning,
    )
    return final, all_sources


@app.post("/api/chat")
async def chat(req: ChatRequest):
    global current_provider
    try:
        context = ""
        docs = []
        if req.mode == "rag" and req.collection:
            query = req.messages[-1].content if req.messages else ""
            if query:
                docs = await rag.search_collection(req.collection, query)
                if docs:
                    context = (
                        "Контекст из документов:\n"
                        + "\n---\n".join(d["content"] for d in docs)
                        + "\n---\nОтветь на вопрос на основе контекста выше."
                    )

        messages = _build_messages(req)

        if req.mode == "agent":
            if not mcp_host.is_ready:
                # fallback to direct chat
                resp = await current_provider.chat(
                    messages, system_prompt="",
                    temperature=req.temperature, max_tokens=req.max_tokens,
                    top_p=req.top_p, reasoning=req.reasoning,
                )
                content, thinking = _extract_thinking(resp)
                return {"role": "assistant", "content": content, "thinking": thinking, "sources": []}

            content, sources = await _run_agent_loop(
                messages,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                top_p=req.top_p,
                reasoning=req.reasoning,
            )
            thinking_full = ""
            final_content = content
            if "<think" in content and "</think>" in content:
                final_content, thinking_full = _extract_thinking(content)
            return {
                "role": "assistant",
                "content": final_content,
                "thinking": thinking_full,
                "sources": sources,
            }

        if context:
            last_q = req.messages[-1].content if req.messages else ""
            messages.append({"role": "user", "content": context + "\n\nВопрос: " + last_q})

        resp = await current_provider.chat(
            messages,
            system_prompt="",
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            top_p=req.top_p,
            reasoning=req.reasoning,
        )
        content, thinking = _extract_thinking(resp)
        return {
            "role": "assistant",
            "content": content,
            "thinking": thinking,
            "sources": docs if req.mode == "rag" else [],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    global current_provider
    try:
        docs = []
        if req.mode == "rag" and req.collection:
            query = req.messages[-1].content if req.messages else ""
            if query:
                docs = await rag.search_collection(req.collection, query)

        messages = _build_messages(req)

        if req.mode == "agent":
            if not mcp_host.is_ready:
                # stream directly without tools
                async def pass_through():
                    async for token in current_provider.chat_stream(
                        messages, system_prompt="",
                        temperature=req.temperature, max_tokens=req.max_tokens,
                        top_p=req.top_p, reasoning=req.reasoning,
                    ):
                        if not token:
                            continue
                        yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"
                    import time
                    elapsed = time.time()
                    fallback_done = {
                        "token": "", "done": True, "full": "", "thinking": "",
                        "sources": [],
                        "metrics": {"time_sec": 0, "tokens": 0, "output_time_sec": 0, "output_tokens": 0, "tokens_per_sec": 0},
                    }
                    yield f"data: {json.dumps(fallback_done)}\n\n"
                return StreamingResponse(pass_through(), media_type="text/event-stream")

            # Agent mode: run tool loop, then emit final content directly
            final_content, sources = await _run_agent_loop(
                messages,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                top_p=req.top_p,
                reasoning=req.reasoning,
            )

            async def generate_agent():
                import re
                content_only = final_content
                thinking_full = ""
                if "<think" in final_content and "</think>" in final_content:
                    thinking_parts = re.findall(r"<think[\s\S]*?</think>", final_content)
                    thinking_full = "".join(thinking_parts)
                    content_only = re.sub(r"<think[\s\S]*?</think>", "", final_content)

                words = content_only.split(" ")
                for i, w in enumerate(words):
                    token = w + (" " if i < len(words) - 1 else "")
                    yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"

                done_data = {
                    "token": "", "done": True, "full": content_only,
                    "thinking": thinking_full, "sources": sources,
                    "metrics": {
                        "time_sec": 0, "tokens": len(words),
                        "output_time_sec": 0, "output_tokens": len(words),
                        "tokens_per_sec": 0,
                    },
                }
                yield f"data: {json.dumps(done_data)}\n\n"

            return StreamingResponse(generate_agent(), media_type="text/event-stream")

        if docs:
            context = (
                "Контекст из документов:\n"
                + "\n---\n".join(d["content"] for d in docs)
                + "\n---\nОтветь на вопрос на основе контекста выше."
            )
            last_q = req.messages[-1].content if req.messages else ""
            messages.append({"role": "user", "content": context + "\n\nВопрос: " + last_q})

        async def generate():
            full = ""
            token_count = 0
            output_tokens = 0
            output_start = None
            start_time = __import__("time").time()
            lm_stats = None

            async for token in current_provider.chat_stream(
                messages,
                system_prompt="",
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                top_p=req.top_p,
                reasoning=req.reasoning,
            ):
                if not token:
                    continue

                if token.startswith("__LMSTATS__") and token.endswith("__LMSTATS__"):
                    lm_stats = json.loads(token[len("__LMSTATS__"):-len("__LMSTATS__")])
                    continue

                full += token
                token_count += 1

                if output_start is not None:
                    output_tokens += 1

                yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"

                if output_start is None and "<think" not in full:
                    output_start = __import__("time").time()

            elapsed = __import__("time").time() - start_time

            import re
            content_only = full
            thinking_full = ""
            if "<think" in full and "</think>" in full:
                thinking_parts = re.findall(r"<think[\s\S]*?</think>", full)
                thinking_full = "".join(thinking_parts)
                content_only = re.sub(r"<think[\s\S]*?</think>", "", full)

            has_thinking = bool(thinking_full)
            if has_thinking and output_start is None:
                output_start = start_time
            if not has_thinking:
                output_tokens = token_count
            output_elapsed = __import__("time").time() - output_start if output_start else elapsed
            tokens_per_sec = round(output_tokens / output_elapsed, 1) if output_elapsed > 0 and output_tokens > 0 else 0

            sources_data = []
            for d in docs:
                sources_data.append({
                    "content": d["content"][:200] + ("..." if len(d["content"]) > 200 else ""),
                    "filename": d["filename"],
                })

            metrics = {
                "time_sec": round(elapsed, 1),
                "tokens": token_count,
                "output_time_sec": round(output_elapsed, 1),
                "output_tokens": output_tokens,
                "tokens_per_sec": tokens_per_sec,
            }
            if lm_stats:
                metrics["input_tokens"] = lm_stats.get("input_tokens", 0)
                metrics["reasoning_tokens"] = lm_stats.get("reasoning_output_tokens", 0)
                metrics["lm_tokens_per_sec"] = round(lm_stats.get("tokens_per_second", 0), 1)
                metrics["ttft"] = round(lm_stats.get("time_to_first_token_seconds", 0), 2)

            done_data = {
                "token": "",
                "done": True,
                "full": content_only,
                "thinking": thinking_full,
                "sources": sources_data,
                "metrics": metrics,
            }
            yield f"data: {json.dumps(done_data)}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- RAG / Collections endpoints ---

@app.get("/api/collections")
async def get_collections():
    try:
        cols = await rag.list_collections()
        return {"collections": cols}
    except Exception as e:
        return {"collections": [], "error": str(e)}


@app.post("/api/collections")
async def create_collection(name: str):
    try:
        return await rag.create_collection(name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/collections/{name}")
async def delete_collection(name: str):
    try:
        return await rag.delete_collection(name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/collections/{name}/documents")
async def get_documents(name: str):
    try:
        docs = await rag.get_collection_documents(name)
        return {"documents": docs}
    except Exception as e:
        return {"documents": [], "error": str(e)}


@app.post("/api/collections/{name}/documents")
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


# --- Workspace endpoints (deferred, basic CRUD) ---

WORKSPACES = []  # in-memory for now
_next_id = 1


@app.get("/api/workspaces")
async def list_workspaces():
    return {"workspaces": WORKSPACES}


@app.post("/api/workspaces")
async def create_workspace(data: dict):
    global _next_id
    ws = {
        "id": _next_id,
        "name": data.get("name", "Новое пространство"),
        "provider": data.get("provider", "ollama"),
        "chat_model": data.get("chat_model", ""),
        "embedding_model": data.get("embedding_model", ""),
        "system_prompt": data.get("system_prompt", ""),
        "temperature": data.get("temperature", 0.7),
        "max_tokens": data.get("max_tokens", 4096),
        "top_p": data.get("top_p", 0.9),
        "context_length": data.get("context_length", 8192),
        "collections": data.get("collections", []),
    }
    _next_id += 1
    WORKSPACES.append(ws)
    return ws


@app.get("/api/workspaces/{ws_id}")
async def get_workspace(ws_id: int):
    for ws in WORKSPACES:
        if ws["id"] == ws_id:
            return ws
    raise HTTPException(status_code=404, detail="Workspace not found")


@app.put("/api/workspaces/{ws_id}")
async def update_workspace(ws_id: int, data: dict):
    for ws in WORKSPACES:
        if ws["id"] == ws_id:
            ws.update(data)
            return ws
    raise HTTPException(status_code=404, detail="Workspace not found")


@app.delete("/api/workspaces/{ws_id}")
async def delete_workspace(ws_id: int):
    global WORKSPACES
    WORKSPACES = [ws for ws in WORKSPACES if ws["id"] != ws_id]
    return {"status": "ok"}
