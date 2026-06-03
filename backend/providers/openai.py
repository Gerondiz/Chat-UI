import json
import httpx
from .base import BaseProvider


class OpenAIProvider(BaseProvider):
    def __init__(self, base_url: str, chat_model: str, embedding_model: str, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(timeout=120, headers=headers)

    async def chat(
        self, messages, system_prompt="",
        temperature=0.7, max_tokens=4096, top_p=0.9,
        reasoning=True,
    ) -> str:
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
        resp = await self._client.post(f"{self.base_url}/chat/completions", json=body)
        resp.raise_for_status()
        data = resp.json()
        await resp.aclose()
        return data["choices"][0]["message"]["content"]

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
        }
        async with self._client.stream("POST", f"{self.base_url}/chat/completions", json=body) as resp:
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                if line.startswith("data: "):
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "") or ""
                        reasoning = delta.get("reasoning_content", "") or ""
                        if not reasoning:
                            reasoning = delta.get("reasoning", "") or ""
                        if reasoning:
                            yield f"<think>{reasoning}</think>"
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

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
