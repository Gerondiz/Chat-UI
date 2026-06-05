from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    id: str = ""
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatResult:
    content: str
    tool_calls: list[ToolCall] | None = None


class BaseProvider(ABC):
    @abstractmethod
    async def chat(
        self, messages: list[dict], system_prompt: str = "",
        temperature: float = 0.7, max_tokens: int = 4096, top_p: float = 0.9,
        reasoning: bool = True,
    ) -> str:
        ...

    async def chat_with_tools(
        self, messages: list[dict], system_prompt: str = "",
        temperature: float = 0.7, max_tokens: int = 4096, top_p: float = 0.9,
        reasoning: bool = True,
        tools: list[dict] | None = None,
    ) -> ChatResult:
        content = await self.chat(
            messages, system_prompt, temperature, max_tokens, top_p, reasoning,
        )
        return ChatResult(content=content)

    def format_assistant_message(
        self, content: str | None, tool_calls: list[ToolCall] | None
    ) -> dict:
        """Build assistant message with tool_calls in provider-specific format."""
        import json
        msg: dict = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id if tc.id else f"call_{i}",
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments) if isinstance(tc.arguments, dict) else tc.arguments,
                    },
                }
                for i, tc in enumerate(tool_calls)
            ]
        return msg

    def format_tool_messages(
        self, tool_calls: list[ToolCall], results: list[str]
    ) -> list[dict]:
        """Build tool result messages in provider-specific format."""
        return [
            {"role": "tool", "content": results[i]}
            for i in range(len(tool_calls))
        ]

    @abstractmethod
    async def chat_stream(
        self, messages: list[dict], system_prompt: str = "",
        temperature: float = 0.7, max_tokens: int = 4096, top_p: float = 0.9,
        reasoning: bool = True,
    ):
        ...

    @abstractmethod
    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        ...

    @abstractmethod
    async def list_models(self) -> tuple[list[str], list[str]]:
        ...

    @abstractmethod
    async def check(self) -> bool:
        ...
