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
from utils import build_messages, extract_thinking, resolve_context_length


async def _apply_context_limit(req: ChatRequest, provider) -> None:
    """Cap the requested context window at what the model is loaded with."""
    req.context_length = resolve_context_length(
        req.context_length,
        await provider.model_context_length(),
    )
from streaming import compute_stream_metrics, sse_token, sse_done, sse_step


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

        await _apply_context_limit(req, state.provider)
        messages = build_messages(req)

        if req.mode == "agent":
            if not mcp_host.is_ready:
                result = await state.provider.chat(
                    messages, system_prompt="",
                    temperature=req.temperature, max_tokens=req.max_tokens,
                    top_p=req.top_p, reasoning=req.reasoning,
                )
                content, thinking = extract_thinking(result.content)
                return {"role": "assistant", "content": content, "thinking": thinking, "sources": []}

            content, sources, msgs, _finish = await run_agent_loop(
                state,
                messages,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                top_p=req.top_p,
                reasoning=req.reasoning,
            )
            if content is None and msgs:
                result = await state.provider.chat(
                    msgs, system_prompt="",
                    temperature=req.temperature, max_tokens=req.max_tokens,
                    top_p=req.top_p, reasoning=req.reasoning,
                )
                content = result.content
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

        result = await state.provider.chat(
            messages,
            system_prompt="",
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            top_p=req.top_p,
            reasoning=req.reasoning,
        )
        content, thinking = extract_thinking(result.content)
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

        await _apply_context_limit(req, state.provider)
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

            async def emit_agent():
                loop_start = time.monotonic()
                progress: asyncio.Queue = asyncio.Queue()
                tag_open = False
                token_count = 0
                reasoning_tokens = 0
                iteration_count = 0
                lm_stats: dict | None = None

                async def on_step(event: dict) -> None:
                    await progress.put(("step", event))

                async def on_delta(event: dict) -> None:
                    await progress.put(("delta", event))

                async def run_loop():
                    return await run_agent_loop(
                        state,
                        messages,
                        temperature=req.temperature,
                        max_tokens=req.max_tokens,
                        top_p=req.top_p,
                        reasoning=req.reasoning,
                        on_step=on_step,
                        on_delta=on_delta,
                    )

                task = asyncio.create_task(run_loop())
                while True:
                    getter = asyncio.ensure_future(progress.get())
                    await asyncio.wait({getter, task}, return_when=asyncio.FIRST_COMPLETED)
                    if getter.done():
                        kind, event = getter.result()
                        if kind == "step":
                            if event.get("kind") == "turn_end":
                                # Close an open think block before the buffer
                                # is dropped, so the parser stays in sync.
                                if tag_open:
                                    tag_open = False
                                    yield sse_token("</think>")
                                if event.get("discard_content"):
                                    yield sse_token("__RESET__")
                            elif event.get("kind") == "iteration":
                                iteration_count = event.get("index", iteration_count)
                            yield sse_step(
                                {k: v for k, v in event.items() if k != "turn_end"}
                            )
                        else:
                            text = event.get("text") or ""
                            if not text:
                                continue
                            token_count += 1
                            if event.get("kind") == "reasoning":
                                reasoning_tokens += 1
                                if not tag_open:
                                    tag_open = True
                                    yield sse_token("<think>")
                                yield sse_token(text)
                            else:
                                if tag_open:
                                    tag_open = False
                                    yield sse_token("</think>")
                                yield sse_token(text)
                        continue
                    getter.cancel()
                    break
                agent_content, sources, agent_msgs, finish_reason = task.result()

                if agent_content is not None:
                    if tag_open:
                        tag_open = False
                        yield sse_token("</think>")
                    # The answer was already streamed live as it was generated.
                    content_only, thinking_full = extract_thinking(agent_content)
                    if not content_only.strip() and thinking_full:
                        content_only = thinking_full.replace("<think>", "").replace("</think>", "").strip()
                        thinking_full = ""

                    elapsed = round(time.monotonic() - loop_start, 2)
                    lm_output = (lm_stats or {}).get("output_tokens", 0)
                    done_data = {
                        "token": "", "done": True, "full": content_only,
                        "thinking": thinking_full, "sources": sources,
                        "metrics": {
                            "time_sec": elapsed,
                            "tokens": lm_output or token_count,
                            "output_time_sec": elapsed,
                            "output_tokens": lm_output or token_count,
                            "tokens_per_sec": (
                                round((lm_output or token_count) / elapsed, 1) if elapsed > 0 else 0
                            ),
                            "input_tokens": (lm_stats or {}).get("input_tokens", 0),
                            "reasoning_tokens": reasoning_tokens,
                            "tool_iterations": iteration_count,
                            **({"finish_reason": finish_reason} if finish_reason else {}),
                        },
                    }
                    yield f"data: {json.dumps(done_data)}\n\n"
                    return

                # iteration cap hit: stream one final answer without tools
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

            return StreamingResponse(emit_agent(), media_type="text/event-stream")

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
