import json
import httpx
from .base import BaseProvider


class LMStudioProvider(BaseProvider):
    def __init__(self, base_url: str, chat_model: str, embedding_model: str, api_key: str = ""):
        base = base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        self.base_url = base
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(timeout=120, headers=headers)

    async def _post(self, path: str, data: dict):
        url = f"{self.base_url}{path}"
        resp = await self._client.post(url, json=data)
        resp.raise_for_status()
        data = resp.json()
        await resp.aclose()
        return data

    def _build_body(self, messages, system_prompt="",
                    temperature=0.7, max_tokens=4096, top_p=0.9,
                    stream=False, reasoning=True):
        parts = []
        if system_prompt:
            parts.append(f"System: {system_prompt}")
        for msg in messages:
            role = msg["role"].capitalize()
            parts.append(f"{role}: {msg['content']}")
        input_text = "\n".join(parts) if parts else ""
        body = {
            "model": self.chat_model,
            "input": input_text,
            "temperature": temperature,
            "max_output_tokens": max_tokens,
            "top_p": top_p,
            "stream": stream,
        }
        if system_prompt:
            body["system_prompt"] = system_prompt
        if not reasoning:
            body["reasoning"] = "off"
        return body

    async def chat(self, messages, system_prompt="",
                   temperature=0.7, max_tokens=4096, top_p=0.9,
                   reasoning=True) -> str:
        body = self._build_body(messages, system_prompt, temperature, max_tokens, top_p, reasoning=reasoning)
        data = await self._post("/api/v1/chat", body)
        full = ""
        for item in data.get("output", []):
            if item.get("type") == "message":
                full += item.get("content", "")
        return full

    async def chat_stream(self, messages, system_prompt="",
                          temperature=0.7, max_tokens=4096, top_p=0.9,
                          reasoning=True):
        body = self._build_body(messages, system_prompt, temperature, max_tokens, top_p, stream=True, reasoning=reasoning)
        url = f"{self.base_url}/api/v1/chat"
        async with self._client.stream("POST", url, json=body) as resp:
            buf = ""
            current_event = ""
            async for chunk in resp.aiter_bytes():
                buf += chunk.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line.startswith("event: "):
                        current_event = line[7:].strip()
                    elif line.startswith("data: "):
                        payload = line[6:].strip()
                        try:
                            if current_event == "reasoning.delta":
                                d = json.loads(payload)
                                content = d.get("content", "")
                                if content:
                                    yield f"<think>{content}</think>"
                            elif current_event == "message.delta":
                                d = json.loads(payload)
                                content = d.get("content", "")
                                if content:
                                    yield content
                            elif current_event == "chat.end":
                                d = json.loads(payload)
                                result = d.get("result", {})
                                stats = result.get("stats", {})
                                if stats:
                                    yield f"__LMSTATS__{json.dumps(stats)}__LMSTATS__"
                        except json.JSONDecodeError:
                            pass

    async def embeddings(self, texts):
        body = {"model": self.embedding_model, "input": texts}
        resp = await self._client.post(f"{self.base_url}/api/v1/embeddings", json=body)
        resp.raise_for_status()
        data = resp.json()
        await resp.aclose()
        return [e["embedding"] for e in data.get("data", [])]

    async def list_models(self) -> tuple[list[str], list[str]]:
        chat_models = []
        embedding_models = []
        try:
            resp = await self._client.get(f"{self.base_url}/api/v1/models")
            resp.raise_for_status()
            data = resp.json()
            models = data.get("models") or data.get("data", [])
            for m in models:
                name = m.get("id") or m.get("key", "")
                if not name:
                    continue
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
            resp = await self._client.get(f"{self.base_url}/api/v1/models")
            ok = resp.status_code == 200
            if ok:
                data = resp.json()
                ok = "error" not in data
            await resp.aclose()
            return ok
        except Exception:
            return False
