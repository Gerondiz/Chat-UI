import logging
from collections.abc import Awaitable, Callable

from mcp_host import mcp_host
from state import AppState

logger = logging.getLogger(__name__)

AGENT_SYSTEM_PROMPT = (
    "Ты — полезный ассистент с доступом к инструментам. "
    "Отвечай на русском языке.\n\n"
    "Правила работы с изображениями:\n"
    "- Когда ты вызываешь search_images, результат уже содержит "
    "готовый markdown: ![описание](url) — скопируй эту строку в свой ответ.\n"
    "- ТЫ ОБЯЗАН показать картинки в ответе. Не описывай их словами — "
    "вставь markdown-строку как есть.\n"
    "- Если картинок несколько — покажи их все, каждую на отдельной строке.\n"
    "- НЕ пиши «вот изображения», «представляю вашему вниманию» или "
    "«наслаждайтесь видами» — просто вставь markdown.\n\n"
    "Правила работы с веб-поиском:\n"
    "- Используй search_web для поиска актуальной информации.\n"
    "- В результатах поиска есть содержимое страниц (content) — используй его для ответа.\n"
    "- ОДИН поиск — достаточно. Не вызывай инструменты повторно с тем же или похожим "
    "запросом: получив результаты, сразу отвечай пользователю.\n"
    "- Не более 2 инструментов подряд. Задача выполнена, когда у тебя есть ответ."
)


async def _answer_from_sources(
    state: AppState,
    messages: list[dict],
    all_sources: list[dict],
    temperature: float,
    max_tokens: int,
    top_p: float,
    reasoning: bool,
    on_delta: Callable[[dict], Awaitable[None]] | None = None,
) -> str | None:
    """Last-resort answer built from collected tool results, no tools involved."""
    excerpts = "\n\n".join(
        f"[{s.get('filename', '')}] {s.get('content', '')}" for s in all_sources[-6:]
    )
    prompt = [
        *messages,
        {
            "role": "user",
            "content": (
                "Инструменты больше недоступны из-за таймаута. "
                "Ответь на исходный вопрос, опираясь только на эти результаты:\n\n"
                f"{excerpts}"
            ),
        },
    ]
    try:
        async def forward(delta) -> None:
            if on_delta is None:
                return
            await on_delta({"kind": delta.kind, "text": delta.text})

        result = await state.provider.chat_with_tools_stream(
            prompt,
            system_prompt=AGENT_SYSTEM_PROMPT,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            reasoning=reasoning,
            tools=None,
            on_delta=forward,
        )
        return result.content
    except Exception as exc:
        logger.error("answer from sources also failed: %s", exc)
        return None


async def run_agent_loop(
    state: AppState,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    top_p: float,
    reasoning: bool,
    max_iterations: int = 3,
    on_step: Callable[[dict], Awaitable[None]] | None = None,
    on_delta: Callable[[dict], Awaitable[None]] | None = None,
) -> tuple[str | None, list[dict], list[dict], str | None]:
    async def emit(event: dict) -> None:
        if on_step is None:
            return
        try:
            await on_step(event)
        except Exception as exc:
            logger.warning("on_step callback failed: %s", exc)

    async def emit_delta(delta) -> None:
        if on_delta is None:
            return
        try:
            await on_delta({"kind": delta.kind, "text": delta.text})
        except Exception as exc:
            logger.warning("on_delta callback failed: %s", exc)

    all_sources: list[dict] = []
    current_messages = list(messages)
    tool_schemas = mcp_host.get_tool_schemas()
    provider = state.provider

    for iteration in range(max_iterations):
        await emit({
            "kind": "iteration",
            "index": iteration + 1,
            "max": max_iterations,
        })
        try:
            result = await provider.chat_with_tools_stream(
                current_messages,
                system_prompt=AGENT_SYSTEM_PROMPT,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                reasoning=reasoning,
                tools=tool_schemas,
                on_delta=emit_delta,
            )
        except Exception as exc:
            logger.warning("chat_with_tools failed (%s), falling back to direct chat", exc)
            logger.info("chat_with_tools exception type: %s, args: %s, repr: %r",
                        type(exc).__name__, exc.args, repr(exc))
            # The failed turn may have streamed partial text; drop it.
            await emit({"kind": "turn_end", "discard_content": True})
            try:
                result = await provider.chat_with_tools_stream(
                    current_messages,
                    system_prompt=AGENT_SYSTEM_PROMPT,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    reasoning=reasoning,
                    tools=None,
                    on_delta=emit_delta,
                )
                return result.content, all_sources, [], result.finish_reason
            except Exception as fallback_exc:
                logger.error("fallback chat also failed (%s)", fallback_exc)
                logger.info("fallback exception type: %s, args: %s, repr: %r",
                            type(fallback_exc).__name__, fallback_exc.args, repr(fallback_exc))
                if iteration > 0 and all_sources:
                    # We already have tool results; answer from them instead of failing.
                    summary = await _answer_from_sources(
                        state, messages, all_sources,
                        temperature, max_tokens, top_p, reasoning, on_delta)
                    if summary is not None:
                        return summary, all_sources, [], None
                raise

        assistant_msg = provider.format_assistant_message(
            "" if result.tool_calls else result.content,
            result.tool_calls,
        )
        current_messages.append(assistant_msg)

        if not result.tool_calls:
            await emit({"kind": "turn_end", "discard_content": False})
            return result.content, all_sources, [], result.finish_reason

        # The model asked for tools: whatever it streamed as prose belongs to
        # the intermediate turn, not to the final answer.
        await emit({"kind": "turn_end", "discard_content": True})

        text_results: list[str] = []
        for tc in result.tool_calls:
            await emit({
                "kind": "tool",
                "name": tc.name,
                "query": tc.arguments.get("query") or tc.arguments.get("collection_name", ""),
            })
            try:
                mcp_results = await mcp_host.call_tool(tc.name, tc.arguments)
                text = "\n".join(r.text for r in mcp_results)
                text_results.append(text or "No results")
                for r in mcp_results:
                    all_sources.append({
                        "content": r.text[:200],
                        "filename": tc.arguments.get("collection_name") or tc.arguments.get("query", tc.name),
                    })
            except Exception as exc:
                text_results.append(f"Error executing tool '{tc.name}': {exc}")
                logger.error("Tool call failed: %s(%s) — %s", tc.name, tc.arguments, exc)

        tool_messages = provider.format_tool_messages(result.tool_calls, text_results)
        current_messages.extend(tool_messages)

    return None, all_sources, current_messages, None
