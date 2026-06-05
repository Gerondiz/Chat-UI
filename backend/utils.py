import re

from models import ChatRequest


def build_messages(req: ChatRequest) -> list[dict]:
    msgs = [m.model_dump() for m in req.messages]
    if req.system_prompt:
        msgs.insert(0, {"role": "system", "content": req.system_prompt})
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
