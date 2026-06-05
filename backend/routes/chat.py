import asyncio
import json
import time
import logging

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse

import rag
from models import ChatRequest
from mcp_host import mcp_host
from state import AppState
from agent import run_agent_loop
from utils import build_messages, extract_thinking
from streaming import compute_stream_metrics, sse_token, sse_done


logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


def _get_state(request: Request) -> AppState:
    return request.app.state.state


@router.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    state = _get_state(request)
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

        messages = build_messages(req)

        if req.mode == "agent":
            if not mcp_host.is_ready:
                resp = await state.provider.chat(
                    messages, system_prompt="",
                    temperature=req.temperature, max_tokens=req.max_tokens,
                    top_p=req.top_p, reasoning=req.reasoning,
                )
                content, thinking = extract_thinking(resp)
                return {"role": "assistant", "content": content, "thinking": thinking, "sources": []}

            content, sources, msgs = await run_agent_loop(
                state,
                messages,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                top_p=req.top_p,
                reasoning=req.reasoning,
            )
            if content is None and msgs:
                content = await state.provider.chat(
                    msgs, system_prompt="",
                    temperature=req.temperature, max_tokens=req.max_tokens,
                    top_p=req.top_p, reasoning=req.reasoning,
                )
            final_content, thinking_full = extract_thinking(content or "")
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

        resp = await state.provider.chat(
            messages,
            system_prompt="",
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            top_p=req.top_p,
            reasoning=req.reasoning,
        )
        content, thinking = extract_thinking(resp)
        return {
            "role": "assistant",
            "content": content,
            "thinking": thinking,
            "sources": docs if req.mode == "rag" else [],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    state = _get_state(request)
    try:
        docs = []
        if req.mode == "rag" and req.collection:
            query = req.messages[-1].content if req.messages else ""
            if query:
                docs = await rag.search_collection(req.collection, query)

        messages = build_messages(req)

        if req.mode == "agent":
            if not mcp_host.is_ready:
                async def pass_through():
                    start = time.monotonic()
                    full = ""
                    token_count = 0
                    output_tokens = 0
                    output_start = None
                    lm_stats = None

                    async for token in state.provider.chat_stream(
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
                        yield sse_token(token)
                        if output_start is None and "<think" not in token:
                            output_start = time.monotonic()

                    content_only, thinking_full, metrics = compute_stream_metrics(
                        start, output_start, token_count, output_tokens, full, lm_stats,
                    )
                    yield sse_done(content_only or "", thinking_full, [], metrics)
                return StreamingResponse(pass_through(), media_type="text/event-stream")

            agent_content, sources, agent_msgs = await run_agent_loop(
                state,
                messages,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                top_p=req.top_p,
                reasoning=req.reasoning,
            )

            if agent_content is not None:
                agent_start = time.monotonic()

                async def emit_agent():
                    nonlocal agent_start
                    content_only, thinking_full = extract_thinking(agent_content)
                    thinking_text = thinking_full.replace("<think>", "").replace("</think>", "").strip() if thinking_full else ""

                    if not content_only.strip() and thinking_full:
                        content_only = thinking_text
                        thinking_full = ""

                    if thinking_text:
                        yield sse_token("<think>")
                        twords = thinking_text.split(" ")
                        for i, w in enumerate(twords):
                            token = w + (" " if i < len(twords) - 1 else "")
                            yield sse_token(token)
                            await asyncio.sleep(0.03)
                        yield sse_token("</think>")

                    words = content_only.split(" ")
                    char_count = len(content_only)
                    for i, w in enumerate(words):
                        token = w + (" " if i < len(words) - 1 else "")
                        yield sse_token(token)
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

            async def stream_agent():
                t0 = time.monotonic()
                full = ""
                token_count = 0
                output_tokens = 0
                output_start = None
                lm_stats = None

                async for token in state.provider.chat_stream(
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
                    yield sse_token(token)
                    if output_start is None and "<think" not in token:
                        output_start = time.monotonic()

                content_only, thinking_full, metrics = compute_stream_metrics(
                    t0, output_start, token_count, output_tokens, full, lm_stats,
                )
                yield sse_done(content_only, thinking_full, sources, metrics)

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

            async for token in state.provider.chat_stream(
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
                yield sse_token(token)
                if output_start is None and "<think" not in token:
                    output_start = time.monotonic()

            content_only, thinking_full, metrics = compute_stream_metrics(
                start_time, output_start, token_count, output_tokens, full, lm_stats,
            )

            sources_data = []
            for d in docs:
                sources_data.append({
                    "content": d["content"][:200] + ("..." if len(d["content"]) > 200 else ""),
                    "filename": d["filename"],
                })

            yield sse_done(content_only, thinking_full, sources_data, metrics)

        return StreamingResponse(generate(), media_type="text/event-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
