import json
import httpx
import config
from .base import BaseProvider, ChatResult, Delta, ToolCall, _maybe_await


def _timeout() -> float:
    return config.PROVIDER_TIMEOUT


class OpenAIProvider(BaseProvider):
    def __init__(self, base_url: str, chat_model: str, embedding_model: str, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(timeout=_timeout(), headers=headers)

    async def chat(
        self, messages, system_prompt="",
        temperature=0.7, max_tokens=4096, top_p=0.9,
        reasoning=True, tools=None,
    ) -> ChatResult:
        msgs = list(messages)
        if system_prompt:
            msgs.insert(0, {"role": "system", "content": system_prompt})
        body = {
            "model": self.chat_model,
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "stream": False,
        }
        if tools:
            body["tools"] = tools
        resp = await self._client.post(f"{self.base_url}/chat/completions", json=body)
        resp.raise_for_status()
        data = resp.json()
        await resp.aclose()
        choice = data["choices"][0]["message"]
        content = choice.get("content") or ""
        rc = choice.get("reasoning_content") or ""
        if rc:
            content = f"<think>{rc}</think>{content}"
        raw_calls = choice.get("tool_calls")
        tool_calls = None
        if raw_calls:
            tool_calls = []
            for tc in raw_calls:
                func = tc.get("function", {})
                tool_calls.append(
                    ToolCall(
                        id=tc.get("id", ""),
                        name=func.get("name", ""),
                        arguments=json.loads(func.get("arguments", "{}")),
                    )
                )
        return ChatResult(content=content, tool_calls=tool_calls or None)

    def format_tool_messages(self, tool_calls, results):
        return [
            {"role": "tool", "content": results[i], "tool_call_id": tc.id or f"call_{i}"}
            for i, tc in enumerate(tool_calls)
        ]

    async def chat_stream(
        self, messages, system_prompt="",
        temperature=0.7, max_tokens=4096, top_p=0.9,
        reasoning=True,
    ):
        msgs = list(messages)
        if system_prompt:
            msgs.insert(0, {"role": "system", "content": system_prompt})
        body = {
            "model": self.chat_model,
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        async with self._client.stream("POST", f"{self.base_url}/chat/completions", json=body) as resp:
            reasoning_open = False
            reasoning_tokens_count = 0
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                if line.startswith("data: "):
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        if reasoning_open:
                            yield "</think>"
                        break
                    try:
                        chunk = json.loads(payload)
                        usage = chunk.get("usage")
                        if usage:
                            if reasoning_open:
                                yield "</think>"
                                reasoning_open = False
                            stats = {
                                "input_tokens": usage.get("prompt_tokens", 0),
                                "output_tokens": usage.get("completion_tokens", 0),
                                "reasoning_output_tokens": reasoning_tokens_count,
                            }
                            yield f"__LMSTATS__{json.dumps(stats)}__LMSTATS__"
                            continue
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "") or ""
                        reasoning = delta.get("reasoning_content", "") or ""
                        if not reasoning:
                            reasoning = delta.get("reasoning", "") or ""
                        if reasoning:
                            if not reasoning_open:
                                yield "<think>"
                                reasoning_open = True
                            reasoning_tokens_count += 1
                            yield reasoning
                        elif content:
                            if reasoning_open:
                                yield "</think>"
                                reasoning_open = False
                            yield content
                    except json.JSONDecodeError:
                        continue

    async def chat_with_tools_stream(
        self, messages, system_prompt="",
        temperature=0.7, max_tokens=4096, top_p=0.9,
        reasoning=True,
        tools=None,
        on_delta=None,
    ):
        """Tool-capable turn that streams text live.

        Content is reported as it arrives. A turn that ends up calling tools
        cannot be known in advance, so callers must tolerate the content
        being discarded (the agent loop resets its buffer via on_turn_end).
        """
        msgs = list(messages)
        if system_prompt:
            msgs.insert(0, {"role": "system", "content": system_prompt})
        body = {
            "model": self.chat_model,
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "stream": True,
        }
        if tools:
            body["tools"] = tools

        parts: list[str] = []
        reasoning_parts: list[str] = []
        # tool calls arrive as fragments keyed by their position in the array
        raw_calls: dict[int, dict] = {}

        async with self._client.stream("POST", f"{self.base_url}/chat/completions", json=body) as resp:
            async for line in resp.aiter_lines():
                if not line.strip() or not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if chunk.get("usage"):
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}

                content = delta.get("content") or ""
                rc = delta.get("reasoning_content") or delta.get("reasoning") or ""
                if rc:
                    reasoning_parts.append(rc)
                    if on_delta is not None:
                        await _maybe_await(on_delta(Delta(kind="reasoning", text=rc)))
                if content:
                    parts.append(content)
                    if on_delta is not None:
                        await _maybe_await(on_delta(Delta(kind="content", text=content)))

                for tcd in delta.get("tool_calls") or []:
                    slot = raw_calls.setdefault(
                        tcd.get("index", 0),
                        {"id": "", "name": "", "arguments": ""},
                    )
                    if tcd.get("id"):
                        slot["id"] = tcd["id"]
                    func = tcd.get("function") or {}
                    if func.get("name"):
                        slot["name"] = func["name"]
                    if func.get("arguments"):
                        slot["arguments"] += func["arguments"]

        tool_calls = None
        if raw_calls:
            tool_calls = []
            for idx in sorted(raw_calls):
                slot = raw_calls[idx]
                try:
                    args = json.loads(slot["arguments"]) if slot["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(id=slot["id"], name=slot["name"], arguments=args))

        content = "".join(parts)
        rc = "".join(reasoning_parts)
        if rc:
            content = f"<think>{rc}</think>{content}"
        return ChatResult(content=content, tool_calls=tool_calls or None)

    async def embeddings(self, texts):
        body = {"model": self.embedding_model, "input": texts}
        resp = await self._client.post(f"{self.base_url}/embeddings", json=body)
        resp.raise_for_status()
        data = resp.json()
        await resp.aclose()
        return [e["embedding"] for e in data["data"]]

    async def list_models(self) -> tuple[list[str], list[str]]:
        chat_models = []
        embedding_models = []
        try:
            resp = await self._client.get(f"{self.base_url}/models")
            resp.raise_for_status()
            for m in resp.json().get("data", []):
                name = m["id"]
                chat_models.append(name)
                if "embed" in name.lower():
                    embedding_models.append(name)
            await resp.aclose()
        except Exception:
            pass
        if not embedding_models and self.embedding_model:
            embedding_models.append(self.embedding_model)
        return chat_models, embedding_models

    async def check(self) -> bool:
        try:
            resp = await self._client.get(f"{self.base_url}/models")
            ok = resp.status_code == 200
            await resp.aclose()
            return ok
        except Exception:
            return False
