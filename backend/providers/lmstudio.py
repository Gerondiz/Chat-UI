import json
import httpx
from .base import BaseProvider, ChatResult, ToolCall


class LMStudioProvider(BaseProvider):
    def __init__(self, base_url: str, chat_model: str, embedding_model: str, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(timeout=300, headers=headers)

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
        resp = await self._client.post(f"{self.base_url}/v1/chat/completions", json=body)
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

    async def embeddings(self, texts):
        body = {"model": self.embedding_model, "input": texts}
        resp = await self._client.post(f"{self.base_url}/v1/embeddings", json=body)
        resp.raise_for_status()
        data = resp.json()
        await resp.aclose()
        return [e["embedding"] for e in data["data"]]

    async def list_models(self) -> tuple[list[str], list[str]]:
        chat_models = []
        embedding_models = []
        try:
            resp = await self._client.get(f"{self.base_url}/v1/models")
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
            resp = await self._client.get(f"{self.base_url}/v1/models")
            ok = resp.status_code == 200
            await resp.aclose()
            return ok
        except Exception:
            return False
