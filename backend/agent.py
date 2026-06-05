import logging

from mcp_host import mcp_host
from state import AppState

logger = logging.getLogger(__name__)

AGENT_SYSTEM_PROMPT = (
    "Ты — полезный ассистент с доступом к инструментам. "
    "Отвечай на русском языке.\n\n"
    "Правила работы с изображениями:\n"
    "- Если ты вызвал search_images и получил URLs картинок — "
    "ОБЯЗАТЕЛЬНО покажи их в ответе с помощью markdown: ![описание](url)\n"
    "- Вставляй картинки прямо в текст, не предлагай пользователю искать их самостоятельно.\n"
    "- Если картинок несколько — покажи их все.\n\n"
    "Правила работы с веб-поиском:\n"
    "- Используй search_web для поиска актуальной информации.\n"
    "- В результатах поиска есть содержимое страниц (content) — используй его для ответа."
)


async def run_agent_loop(
    state: AppState,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    top_p: float,
    reasoning: bool,
    max_iterations: int = 5,
) -> tuple[str | None, list[dict], list[dict]]:
    all_sources: list[dict] = []
    current_messages = list(messages)
    tool_schemas = mcp_host.get_tool_schemas()
    provider = state.provider

    for iteration in range(max_iterations):
        try:
            result = await provider.chat_with_tools(
                current_messages,
                system_prompt=AGENT_SYSTEM_PROMPT,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                reasoning=reasoning,
                tools=tool_schemas,
            )
        except Exception as exc:
            logger.warning("chat_with_tools failed (%s), falling back to direct chat", exc)
            logger.info("chat_with_tools exception type: %s, args: %s, repr: %r",
                        type(exc).__name__, exc.args, exc)
            try:
                result = await provider.chat(
                    current_messages,
                    system_prompt=AGENT_SYSTEM_PROMPT,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    reasoning=reasoning,
                )
                return result.content, all_sources, []
            except Exception as fallback_exc:
                logger.error("fallback chat also failed (%s)", fallback_exc)
                logger.info("fallback exception type: %s, args: %s, repr: %r",
                            type(fallback_exc).__name__, fallback_exc.args, fallback_exc)
                raise

        assistant_msg = provider.format_assistant_message(
            "" if result.tool_calls else result.content,
            result.tool_calls,
        )
        current_messages.append(assistant_msg)

        if not result.tool_calls:
            return result.content, all_sources, []

        text_results: list[str] = []
        for tc in result.tool_calls:
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

    return None, all_sources, current_messages
