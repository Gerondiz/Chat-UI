import re

from models import ChatRequest


# Rough token estimate: roughly 4 characters per token for Russian and English
# prose. A real tokenizer is not worth pulling in just to keep a request
# inside the model's context window.
_CHARS_PER_TOKEN = 4
_DEFAULT_CONTEXT_LENGTH = 8192


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return len(text) // _CHARS_PER_TOKEN + 1


def _message_tokens(msg: dict) -> int:
    total = 4  # per-message role/format overhead
    total += estimate_tokens(str(msg.get("content") or ""))
    for call in msg.get("tool_calls") or []:
        func = call.get("function") or {}
        total += estimate_tokens(str(func.get("name", "")))
        total += estimate_tokens(str(func.get("arguments", "")))
    return total


def trim_messages(
    msgs: list[dict], context_length: int, reserve: int = 0
) -> tuple[list[dict], int]:
    """Drop the oldest turns until the history fits the context window.

    The system prompt is always kept, and so is the most recent message even
    if it does not fit on its own. Returns the trimmed list and the number of
    dropped messages.
    """
    if context_length <= 0:
        return msgs, 0

    budget = context_length - max(reserve, 0)
    system = [m for m in msgs[:1] if m.get("role") == "system"]
    body = msgs[len(system):]

    budget -= sum(_message_tokens(m) for m in system)

    kept: list[dict] = []
    used = 0
    for msg in reversed(body):
        cost = _message_tokens(msg)
        if kept and used + cost > budget:
            break
        kept.insert(0, msg)
        used += cost

    if not kept and body:
        kept = [body[-1]]

    dropped = len(body) - len(kept)
    return system + kept, dropped


def build_messages(req: ChatRequest) -> list[dict]:
    msgs = [m.model_dump() for m in req.messages]
    if req.system_prompt:
        msgs.insert(0, {"role": "system", "content": req.system_prompt})

    context_length = req.context_length or _DEFAULT_CONTEXT_LENGTH
    msgs, dropped = trim_messages(msgs, context_length, reserve=req.max_tokens)

    if dropped:
        note = (
            f"[{dropped} предыдущих сообщений диалога удалено из-за "
            f"ограничения контекстного окна в {context_length} токенов. "
            f"Учитывай только то, что видно выше.]"
        )
        insert_at = 1 if msgs and msgs[0].get("role") == "system" else 0
        msgs.insert(insert_at, {"role": "system", "content": note})

    return msgs


def extract_thinking(resp: str) -> tuple[str, str]:
    parts = re.findall(r"<think[\s\S]*?</think>", resp)
    if parts:
        thinking = "".join(parts)
        content = re.sub(r"<think[\s\S]*?</think>", "", resp)
        content = content.replace("</think>", "").replace("<think>", "")
        return content.strip(), thinking
    if "</think>" in resp:
        content = resp.replace("</think>", "").strip()
        return content, ""
    if "<think" in resp:
        idx = resp.index("<think")
        content = resp[:idx] + resp[idx + 6:].strip()
        return content, ""
    return resp, ""
