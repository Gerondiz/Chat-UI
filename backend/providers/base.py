from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from inspect import isawaitable
from typing import Any, Callable


async def _maybe_await(value: Any) -> Any:
    """Await the result of a callback if it happens to be a coroutine."""
    if isawaitable(value):
        return await value
    return value


@dataclass
class ToolCall:
    id: str = ""
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatResult:
    content: str
    tool_calls: list[ToolCall] | None = None
    finish_reason: str | None = None  # "length" means the output was cut off


@dataclass
class Delta:
    """Live text fragment produced by a single model turn.

    kind is either "reasoning" or "content". When tools are enabled the
    final content may be discarded if the turn turns out to be a tool call,
    so the consumer must be able to reset its buffers (see AgentTurn).
    """
    kind: str
    text: str


class BaseProvider(ABC):
    @abstractmethod
    async def chat(
        self, messages: list[dict], system_prompt: str = "",
        temperature: float = 0.7, max_tokens: int = 4096, top_p: float = 0.9,
        reasoning: bool = True,
        tools: list[dict] | None = None,
    ) -> ChatResult:
        ...

    async def chat_with_tools(
        self, messages: list[dict], system_prompt: str = "",
        temperature: float = 0.7, max_tokens: int = 4096, top_p: float = 0.9,
        reasoning: bool = True,
        tools: list[dict] | None = None,
    ) -> ChatResult:
        return await self.chat(
            messages, system_prompt, temperature, max_tokens, top_p, reasoning, tools=tools,
        )

    async def chat_with_tools_stream(
        self, messages: list[dict], system_prompt: str = "",
        temperature: float = 0.7, max_tokens: int = 4096, top_p: float = 0.9,
        reasoning: bool = True,
        tools: list[dict] | None = None,
        on_delta: Callable[[Delta], Any] | None = None,
    ) -> ChatResult:
        """Tool-capable turn that reports text as it is generated.

        The default implementation is not streaming: it performs a regular
        tool-capable request and replays the finished text through on_delta.
        Subclasses that can stream should override this.
        """
        result = await self.chat_with_tools(
            messages, system_prompt, temperature, max_tokens, top_p, reasoning, tools=tools,
        )
        if on_delta is None:
            return result

        from utils import extract_thinking

        content, thinking = extract_thinking(result.content)
        if thinking:
            await _maybe_await(on_delta(
                Delta(kind="reasoning", text=thinking.replace("<think>", "").replace("</think>", "").strip())
            ))
        if content:
            await _maybe_await(on_delta(Delta(kind="content", text=content)))
        return result

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

    async def model_context_length(self) -> int:
        """Context window the loaded model can actually accept, 0 if unknown."""
        return 0
