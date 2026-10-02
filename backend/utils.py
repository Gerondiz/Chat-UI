import re

from models import ChatRequest


# Rough token estimate. Cyrillic packs roughly half as many characters per
# token as Latin, so a single flat ratio badly underestimates Russian chats and
# lets the prompt overflow the model's window. Slight overestimation is
# harmless - trimming too eagerly just drops an older turn - while
# underestimation is a hard error upstream.
_CYRILLIC_CHARS_PER_TOKEN = 2
_LATIN_CHARS_PER_TOKEN = 4
_DEFAULT_CONTEXT_LENGTH = 8192


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cyrillic = 0
    for ch in text:
        if "\u0400" <= ch <= "\u04FF":
            cyrillic += 1
    other = len(text) - cyrillic
    return (
        cyrillic // _CYRILLIC_CHARS_PER_TOKEN
        + other // _LATIN_CHARS_PER_TOKEN
        + 1
    )


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

    # A single message can still be larger than the whole window on its own.
    # Keeping it verbatim would be rejected upstream, so cut it as a last
    # resort and mark that it was cut.
    if kept and budget > 0:
        last = kept[-1]
        if _message_tokens(last) > budget:
            content = str(last.get("content") or "")
            last = dict(last)
            marker = "\n[сообщение обрезано по длине контекстного окна]"
            allowance = int((budget - 4) * _CYRILLIC_CHARS_PER_TOKEN)
            while allowance > 64:
                last["content"] = content[:allowance] + marker
                if _message_tokens(last) <= budget:
                    break
                allowance = int(allowance * 0.9)
            else:
                last["content"] = content[:64] + marker
            kept[-1] = last

    dropped = len(body) - len(kept)
    return system + kept, dropped


def resolve_context_length(requested: int, actual: int) -> int:
    """Clamp the requested window to what the loaded model can accept.

    The panel value describes what the user wants, but the server may well
    have the model loaded with a much smaller window. Exceeding that is a hard
    error, not a graceful truncation.
    """
    limit = requested or _DEFAULT_CONTEXT_LENGTH
    if actual > 0:
        limit = min(limit, actual)
    return limit


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
