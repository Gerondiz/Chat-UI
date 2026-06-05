import asyncio
import json
import logging
import re
import time
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
_provider_lock = asyncio.Lock()


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
            chat_model="",
            embedding_model="",
            base_url=config.OLLAMA_BASE_URL,
        )
    if name == "openai":
        return ProviderConfig(
            name="openai",
            chat_model="",
            embedding_model="",
            base_url=config.OPENAI_BASE_URL,
            api_key=config.OPENAI_API_KEY,
        )
    return ProviderConfig(
        name="lmstudio",
        chat_model="",
        embedding_model="",
        base_url=config.LMSTUDIO_BASE_URL,
    )


async def _auto_select_models(provider: BaseProvider, cfg: ProviderConfig) -> ProviderConfig:
    """Fetch available models and pick the first chat model and first embedding model."""
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


@app.on_event("startup")
async def startup():
    global current_provider, current_config
    current_config = _default_config("ollama")
    current_provider = _make_provider(current_config)
    current_config = await _auto_select_models(current_provider, current_config)
    current_provider = _make_provider(current_config)
    # start MCP host in background
    asyncio.create_task(mcp_host.start())
    ready = await mcp_host.wait_ready(timeout=20)
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
    async with _provider_lock:
        return current_config


@app.put("/api/provider")
async def switch_provider(switch: ProviderSwitch):
    global current_provider, current_config
    async with _provider_lock:
        current_config = _default_config(switch.name)
        current_provider = _make_provider(current_config)
        current_config = await _auto_select_models(current_provider, current_config)
        current_provider = _make_provider(current_config)
    return current_config


@app.put("/api/provider/config")
async def update_provider_config(cfg: ProviderConfig):
    global current_provider, current_config
    async with _provider_lock:
        current_config = cfg
        current_provider = _make_provider(cfg)
    return current_config


@app.get("/api/provider/status")
async def provider_status():
    global current_provider, current_config
    async with _provider_lock:
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
    async with _provider_lock:
        chat_models, embedding_models = await current_provider.list_models()
    return {"chat_models": chat_models, "embedding_models": embedding_models}


# --- Chat endpoints ---

def _build_messages(req: ChatRequest) -> list[dict]:
    msgs = [m.model_dump() for m in req.messages]
    if req.system_prompt:
        msgs.insert(0, {"role": "system", "content": req.system_prompt})
    return msgs


def _extract_thinking(resp: str) -> tuple[str, str]:
    parts = re.findall(r"<think[\s\S]*?</think>", resp)
    if parts:
        thinking = "".join(parts)
        content = re.sub(r"<think[\s\S]*?</think>", "", resp)
        content = content.replace("</think>", "").replace("<think>", "")
        return content.strip(), thinking
    if "<think" in resp and " response" in resp:
        t_start = resp.index("<think")
        t_end = resp.rindex(" response") + len(" response")
        thinking = resp[t_start:t_end]
        content = resp[:t_start] + resp[t_end:]
        return content, thinking
    if "</think>" in resp:
        content = resp.replace("</think>", "").strip()
        return content, ""
    if resp.strip().startswith("<think") and "</think>" not in resp:
        content = resp.replace("<think", "").strip()
        return content, ""
    return resp, ""


async def _run_agent_loop(
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    top_p: float,
    reasoning: bool,
    max_iterations: int = 5,
) -> tuple[str | None, list[dict], list[dict]]:
    """Run the agent tool-calling loop. Returns (final_content, all_sources, final_messages).
    If loop ended with content, final_content is set and final_messages is empty.
    If loop ended with tool_call, final_content is None and final_messages should be streamed.
    """
    all_sources: list[dict] = []
    current_messages = list(messages)
    tool_schemas = mcp_host.get_tool_schemas()

    for iteration in range(max_iterations):
        try:
            result = await current_provider.chat_with_tools(
                current_messages,
                system_prompt="",
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                reasoning=reasoning,
                tools=tool_schemas,
            )
        except Exception as exc:
            logger.warning("chat_with_tools failed (%s), falling back to direct chat", exc)
            logger.info("chat_with_tools exception type: %s, args: %s, repr: %r",
                        type(exc).__name__, exc.args, exc)
            try:
                content = await current_provider.chat(
                    current_messages,
                    system_prompt="",
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    reasoning=reasoning,
                )
                return content, all_sources, []
            except Exception as fallback_exc:
                logger.error("fallback chat also failed (%s)", fallback_exc)
                logger.info("fallback exception type: %s, args: %s, repr: %r",
                            type(fallback_exc).__name__, fallback_exc.args, fallback_exc)
                raise

        # Append assistant response to conversation
        assistant_msg = current_provider.format_assistant_message(
            "" if result.tool_calls else result.content,
            result.tool_calls,
        )
        current_messages.append(assistant_msg)

        if not result.tool_calls:
            # No tools called — final response
            return result.content, all_sources, []

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

    # Max iterations reached — return messages for streaming
    return None, all_sources, current_messages


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
                resp = await current_provider.chat(
                    messages, system_prompt="",
                    temperature=req.temperature, max_tokens=req.max_tokens,
                    top_p=req.top_p, reasoning=req.reasoning,
                )
                content, thinking = _extract_thinking(resp)
                return {"role": "assistant", "content": content, "thinking": thinking, "sources": []}

            content, sources, msgs = await _run_agent_loop(
                messages,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                top_p=req.top_p,
                reasoning=req.reasoning,
            )
            if content is None and msgs:
                content = await current_provider.chat(
                    msgs, system_prompt="",
                    temperature=req.temperature, max_tokens=req.max_tokens,
                    top_p=req.top_p, reasoning=req.reasoning,
                )
            final_content, thinking_full = _extract_thinking(content or "")
            if not final_content.strip() and thinking_full:
                final_content = thinking_full.replace("<think>", "").replace("</think>", "")
                thinking_full = ""
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
                    start = time.monotonic()
                    full = ""
                    token_count = 0
                    output_tokens = 0
                    output_start = None
                    lm_stats = None

                    async for token in current_provider.chat_stream(
                        messages, system_prompt="",
                        temperature=req.temperature, max_tokens=req.max_tokens,
                        top_p=req.top_p, reasoning=req.reasoning,
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
                        if output_start is None and "<think" not in token:
                            output_start = time.monotonic()

                    elapsed = round(time.monotonic() - start, 2)
                    content_only, thinking_full = _extract_thinking(full)
                    has_thinking = bool(thinking_full)
                    if has_thinking and output_start is None:
                        output_start = start
                        if output_tokens == 0:
                            output_tokens = token_count
                    if not has_thinking:
                        output_tokens = token_count
                    output_elapsed = round(time.monotonic() - output_start, 2) if output_start else elapsed
                    tps = round(output_tokens / output_elapsed, 1) if output_elapsed > 0 and output_tokens > 0 else 0

                    metrics = {
                        "time_sec": elapsed, "tokens": token_count,
                        "output_time_sec": output_elapsed,
                        "output_tokens": output_tokens,
                        "tokens_per_sec": tps,
                    }
                    if lm_stats:
                        metrics["input_tokens"] = lm_stats.get("input_tokens", 0)
                        lm_out = lm_stats.get("output_tokens", 0)
                        if lm_out:
                            metrics["tokens"] = lm_out
                        metrics["reasoning_tokens"] = lm_stats.get("reasoning_output_tokens", 0)
                        metrics["lm_tokens_per_sec"] = round(lm_stats.get("tokens_per_second", 0), 1)
                        metrics["ttft"] = round(lm_stats.get("time_to_first_token_seconds", 0), 2)

                    fallback_done = {
                        "token": "", "done": True, "full": content_only or "",
                        "thinking": thinking_full, "sources": [],
                        "metrics": metrics,
                    }
                    yield f"data: {json.dumps(fallback_done)}\n\n"
                return StreamingResponse(pass_through(), media_type="text/event-stream")

            # Agent mode: run tool loop, then stream final response
            agent_content, sources, agent_msgs = await _run_agent_loop(
                messages,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                top_p=req.top_p,
                reasoning=req.reasoning,
            )

            if agent_content is not None:
                agent_start = time.monotonic()
                # Response without tool calls — emit directly
                async def emit_agent():
                    content_only, thinking_full = _extract_thinking(agent_content)

                    thinking_text = thinking_full.replace("<think>", "").replace("</think>", "").strip() if thinking_full else ""

                    # If no content but thinking, put thinking in content (fallback)
                    if not content_only.strip() and thinking_full:
                        content_only = thinking_text
                        thinking_full = ""

                    # Stream thinking first (if any) so the thinking block appears progressively
                    if thinking_text:
                        yield f"data: {json.dumps({'token': '<think>', 'done': False})}\n\n"
                        twords = thinking_text.split(" ")
                        for i, w in enumerate(twords):
                            token = w + (" " if i < len(twords) - 1 else "")
                            yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"
                            await asyncio.sleep(0.03)
                        yield f"data: {json.dumps({'token': '</think>', 'done': False})}\n\n"

                    # Stream content words
                    words = content_only.split(" ")
                    char_count = len(content_only)
                    for i, w in enumerate(words):
                        token = w + (" " if i < len(words) - 1 else "")
                        yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"
                        if i < len(words) - 1:
                            await asyncio.sleep(0.03)

                    elapsed = round(time.monotonic() - agent_start, 2)
                    token_est = max(len(words), char_count // 4)
                    done_data = {
                        "token": "", "done": True, "full": content_only,
                        "thinking": thinking_full, "sources": sources,
                        "metrics": {
                            "time_sec": elapsed, "tokens": token_est,
                            "output_time_sec": elapsed, "output_tokens": token_est,
                            "tokens_per_sec": round(token_est / elapsed, 1) if elapsed > 0 else 0,
                            "reasoning_tokens": 0,
                        },
                    }
                    yield f"data: {json.dumps(done_data)}\n\n"

                return StreamingResponse(emit_agent(), media_type="text/event-stream")

            # tool loop ended — stream final response from provider
            async def stream_agent():
                t0 = time.monotonic()
                full = ""
                token_count = 0
                output_tokens = 0
                output_start = None
                lm_stats = None

                async for token in current_provider.chat_stream(
                    agent_msgs, system_prompt="",
                    temperature=req.temperature, max_tokens=req.max_tokens,
                    top_p=req.top_p, reasoning=req.reasoning,
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

                    if output_start is None and "<think" not in token:
                        output_start = time.monotonic()

                elapsed = round(time.monotonic() - t0, 2)
                content_only, thinking_full = _extract_thinking(full)
                if not content_only.strip() and thinking_full:
                    content_only = thinking_full.replace("<think>", "").replace("</think>", "")
                    thinking_full = ""

                has_thinking = bool(thinking_full)
                if has_thinking and output_start is None:
                    output_start = t0
                    if output_tokens == 0:
                        output_tokens = token_count
                if not has_thinking:
                    output_tokens = token_count
                output_elapsed = round(time.monotonic() - output_start, 2) if output_start else elapsed
                tps = round(output_tokens / output_elapsed, 1) if output_elapsed > 0 and output_tokens > 0 else 0

                metrics = {
                    "time_sec": elapsed, "tokens": token_count,
                    "output_time_sec": output_elapsed, "output_tokens": output_tokens,
                    "tokens_per_sec": tps,
                }
                if lm_stats:
                    metrics["input_tokens"] = lm_stats.get("input_tokens", 0)
                    lm_output = lm_stats.get("output_tokens", 0)
                    if lm_output:
                        metrics["tokens"] = lm_output
                    metrics["reasoning_tokens"] = lm_stats.get("reasoning_output_tokens", 0)
                    metrics["lm_tokens_per_sec"] = round(lm_stats.get("tokens_per_second", 0), 1)
                    metrics["ttft"] = round(lm_stats.get("time_to_first_token_seconds", 0), 2)

                done_data = {
                    "token": "", "done": True, "full": content_only,
                    "thinking": thinking_full, "sources": sources,
                    "metrics": metrics,
                }
                yield f"data: {json.dumps(done_data)}\n\n"

            return StreamingResponse(stream_agent(), media_type="text/event-stream")

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
            start_time = time.monotonic()
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

                if output_start is None and "<think" not in token:
                    output_start = time.monotonic()

            elapsed = round(time.monotonic() - start_time, 2)

            content_only, thinking_full = _extract_thinking(full)
            if not content_only.strip() and thinking_full:
                content_only = thinking_full.replace("<think>", "").replace("</think>", "")
                thinking_full = ""
            has_thinking = bool(thinking_full)
            if has_thinking and output_start is None:
                output_start = start_time
                if output_tokens == 0:
                    output_tokens = token_count
            if not has_thinking:
                output_tokens = token_count
            output_elapsed = round(time.monotonic() - output_start, 2) if output_start else elapsed
            tokens_per_sec = round(output_tokens / output_elapsed, 1) if output_elapsed > 0 and output_tokens > 0 else 0

            sources_data = []
            for d in docs:
                sources_data.append({
                    "content": d["content"][:200] + ("..." if len(d["content"]) > 200 else ""),
                    "filename": d["filename"],
                })

            metrics = {
                "time_sec": elapsed,
                "tokens": token_count,
                "output_time_sec": output_elapsed,
                "output_tokens": output_tokens,
                "tokens_per_sec": tokens_per_sec,
            }
            if lm_stats:
                metrics["input_tokens"] = lm_stats.get("input_tokens", 0)
                lm_output = lm_stats.get("output_tokens", 0)
                if lm_output:
                    metrics["tokens"] = lm_output
                metrics["reasoning_tokens"] = lm_stats.get("reasoning_output_tokens", 0)
                tps = lm_stats.get("tokens_per_second")
                if tps:
                    metrics["lm_tokens_per_sec"] = round(tps, 1)
                ttft = lm_stats.get("time_to_first_token_seconds")
                if ttft:
                    metrics["ttft"] = round(ttft, 2)

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
