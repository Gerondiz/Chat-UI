import json
import time
import logging

from fastapi.responses import StreamingResponse

from utils import extract_thinking

logger = logging.getLogger(__name__)


def compute_stream_metrics(
    start: float,
    output_start: float | None,
    token_count: int,
    output_tokens: int,
    full: str,
    lm_stats: dict | None,
) -> tuple[str, str, dict]:
    now = time.monotonic()
    elapsed = round(now - start, 2)

    content_only, thinking_full = extract_thinking(full)
    if not content_only.strip() and thinking_full:
        content_only = thinking_full.replace("<think>", "").replace("</think>", "")
        thinking_full = ""
    has_thinking = bool(thinking_full)

    if has_thinking and output_start is None:
        output_start = start
        if output_tokens == 0:
            output_tokens = token_count
    if not has_thinking:
        output_tokens = token_count

    output_elapsed = round(now - output_start, 2) if output_start else elapsed
    tps = round(output_tokens / output_elapsed, 1) if output_elapsed > 0 and output_tokens > 0 else 0

    metrics = {
        "time_sec": elapsed,
        "tokens": token_count,
        "output_time_sec": output_elapsed,
        "output_tokens": output_tokens,
        "tokens_per_sec": tps,
    }
    if lm_stats:
        metrics["input_tokens"] = lm_stats.get("input_tokens", 0)
        lm_output = lm_stats.get("output_tokens", 0)
        if lm_output:
            metrics["tokens"] = lm_output
        metrics["reasoning_tokens"] = lm_stats.get("reasoning_output_tokens", 0)
        tps_val = lm_stats.get("tokens_per_second")
        if tps_val:
            metrics["lm_tokens_per_sec"] = round(tps_val, 1)
        ttft_val = lm_stats.get("time_to_first_token_seconds")
        if ttft_val:
            metrics["ttft"] = round(ttft_val, 2)

    return content_only, thinking_full, metrics


def sse_token(token: str) -> str:
    return f"data: {json.dumps({'token': token, 'done': False})}\n\n"


def sse_done(content: str, thinking: str, sources: list[dict], metrics: dict) -> str:
    obj = {
        "token": "", "done": True, "full": content,
        "thinking": thinking, "sources": sources, "metrics": metrics,
    }
    return f"data: {json.dumps(obj)}\n\n"
