import json
import httpx
from .base import BaseProvider, ChatResult, ToolCall


class OllamaProvider(BaseProvider):
    def __init__(self, base_url: str, chat_model: str, embedding_model: str):
        self.base_url = base_url.rstrip("/")
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        self._client = httpx.AsyncClient(timeout=120)

    async def _post(self, path: str, data: dict):
        url = f"{self.base_url}{path}"
        resp = await self._client.post(url, json=data)
        try:
            resp.raise_for_status()
            body = resp.content
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                pass
            # NDJSON fallback: accumulate content across lines, take stats from done line
            result = {}
            thinking_parts = []
            for line in body.decode().split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(parsed, dict):
                    continue
                chunk = parsed.get("message", {}) if isinstance(parsed.get("message"), dict) else parsed
                c = chunk.get("content", "") or ""
                if c:
                    prev = result.get("message", {}).get("content", "") if isinstance(result.get("message"), dict) else ""
                    result.setdefault("message", {})["content"] = prev + c
                t = chunk.get("thinking", "") or parsed.get("thinking", "") or ""
                if t:
                    thinking_parts.append(t)
                # Capture tool_calls from any line (may arrive before done:true)
                msg = parsed.get("message", {})
                if isinstance(msg, dict) and msg.get("tool_calls"):
                    result.setdefault("message", {})["tool_calls"] = msg["tool_calls"]
                if parsed.get("done"):
                    for k, v in parsed.items():
                        if k != "message":
                            result[k] = v
                    if not result.get("message", {}).get("content"):
                        if isinstance(msg, dict) and msg.get("content"):
                            result["message"] = dict(msg)
            if thinking_parts:
                thinking_text = "".join(thinking_parts)
                existing = result.get("message", {}).get("content", "") or ""
                result.setdefault("message", {})["content"] = f"<think>{thinking_text}</think>{existing}"
            return result
        finally:
            await resp.aclose()

    async def chat(
        self, messages, system_prompt="",
        temperature=0.7, max_tokens=4096, top_p=0.9,
        reasoning=True,
    ) -> str:
        body = {
            "model": self.chat_model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": max_tokens,
            },
        }
        if system_prompt:
            body["system"] = system_prompt
        data = await self._post("/api/chat", body)
        return data.get("message", {}).get("content", "")

    async def chat_with_tools(
        self, messages, system_prompt="",
        temperature=0.7, max_tokens=4096, top_p=0.9,
        reasoning=True, tools=None,
    ) -> ChatResult:
        body = {
            "model": self.chat_model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": max_tokens,
            },
        }
        if system_prompt:
            body["system"] = system_prompt
        if tools:
            body["tools"] = tools
        data = await self._post("/api/chat", body)
        msg = data.get("message", {})
        content = msg.get("content", "")
        raw_calls = msg.get("tool_calls")
        tool_calls = None
        if raw_calls:
            tool_calls = []
            for tc in raw_calls:
                func = tc.get("function", {})
                tool_calls.append(
                    ToolCall(
                        id=tc.get("id", ""),
                        name=func.get("name", ""),
                        arguments=func.get("arguments", {}),
                    )
                )
        return ChatResult(content=content, tool_calls=tool_calls or None)

    def format_assistant_message(self, content, tool_calls):
        msg = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = [
                {
                    "function": {
                        "name": tc.name,
                        "arguments": tc.arguments if isinstance(tc.arguments, dict) else json.loads(tc.arguments),
                    },
                }
                for tc in tool_calls
            ]
        return msg

    def format_tool_messages(self, tool_calls, results):
        return [
            {"role": "tool", "content": results[i], "name": tc.name}
            for i, tc in enumerate(tool_calls)
        ]

    async def chat_stream(
        self, messages, system_prompt="",
        temperature=0.7, max_tokens=4096, top_p=0.9,
        reasoning=True,
    ):
        body = {
            "model": self.chat_model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": max_tokens,
            },
        }
        if system_prompt:
            body["system"] = system_prompt
        url = f"{self.base_url}/api/chat"
        async with self._client.stream("POST", url, json=body) as resp:
            thinking_buf = []
            thinking_tokens = 0
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                    msg = chunk.get("message", {}) if isinstance(chunk.get("message"), dict) else {}
                    t = chunk.get("thinking", "") or msg.get("thinking", "") or ""
                    delta = msg.get("content", "") or ""

                    if t:
                        thinking_buf.append(t)
                        thinking_tokens += 1
                    elif delta:
                        if thinking_buf:
                            yield f"<think>{''.join(thinking_buf)}</think>"
                            thinking_buf = []
                        yield delta

                    if chunk.get("done"):
                        if thinking_buf:
                            yield f"<think>{''.join(thinking_buf)}</think>"
                        stats = {
                            "input_tokens": chunk.get("prompt_eval_count", 0),
                            "output_tokens": chunk.get("eval_count", 0),
                            "reasoning_output_tokens": thinking_tokens,
                        }
                        eval_dur = chunk.get("eval_duration", 0)
                        if eval_dur:
                            tps = stats["output_tokens"] / (eval_dur / 1e9)
                            if tps > 0:
                                stats["tokens_per_second"] = round(tps, 1)
                        total_dur = chunk.get("total_duration", 0)
                        if total_dur:
                            stats["time_to_first_token_seconds"] = round(total_dur / 1e9, 3)
                        yield f"__LMSTATS__{json.dumps(stats)}__LMSTATS__"
                        break
                except json.JSONDecodeError:
                    continue

    async def embeddings(self, texts):
        data = {"model": self.embedding_model, "input": texts}
        resp = await self._post("/api/embed", data)
        return [e["embedding"] for e in resp.get("embeddings", [])]

    async def list_models(self) -> tuple[list[str], list[str]]:
        chat_models = []
        embedding_models = []
        try:
            resp = await self._client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            for m in resp.json().get("models", []):
                name = m["name"]
                chat_models.append(name)
                if "embed" in name or "nomic" in name:
                    embedding_models.append(name)
            await resp.aclose()
        except Exception:
            pass
        if not embedding_models and self.embedding_model:
            embedding_models.append(self.embedding_model)
        return chat_models, embedding_models

    async def check(self) -> bool:
        try:
            resp = await self._client.get(f"{self.base_url}/api/tags")
            ok = resp.status_code == 200
            await resp.aclose()
            return ok
        except Exception:
            return False
