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
        resp.raise_for_status()
        data = resp.json()
        await resp.aclose()
        return data

    async def chat(
        self, messages, system_prompt="",
        temperature=0.7, max_tokens=4096, top_p=0.9,
        reasoning=True,
    ) -> str:
        body = {
            "model": self.chat_model,
            "messages": messages,
            "stream": False,
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
            "stream": False,
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
                        name=func.get("name", ""),
                        arguments=func.get("arguments", {}),
                    )
                )
        return ChatResult(content=content, tool_calls=tool_calls or None)

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
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                    delta = chunk.get("message", {}).get("content", "")
                    yield delta
                    if chunk.get("done"):
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
