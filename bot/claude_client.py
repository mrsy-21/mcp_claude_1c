"""Agentic loop for the Telegram bot.

Mirrors test_agentic_loop.py but:
- accepts existing history (list[Message]) instead of starting fresh
- returns (answer_text, total_input_tokens, total_output_tokens)
- tools loaded once at module level from FastAPI /metadata
"""

import json
import os

import httpx
import structlog
from dotenv import load_dotenv

load_dotenv()

from llm.base import Message, ToolDefinition
from llm.factory import create_llm_client
from mcp_server.server import _dispatch, _fetch_entity_list, _make_tools

log = structlog.get_logger(__name__)

FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:8000")
MAX_TOOL_ITERATIONS = 8

SYSTEM_PROMPT = """Ти — бухгалтерський асистент з доступом до 1С/BAS.
Відповідай завжди українською мовою.
Поточний рік — 2026. Якщо користувач каже "травень" — маєш на увазі 2026-05-01 по 2026-05-31.
Числа форматуй з роздільниками тисяч (наприклад: 1 234 567.00 грн).
Якщо записів більше 10 — показуй перші 10 і пиши "та ще N записів".

Система: BAS Accounting CORP 2.1 (bas-soft.eu) — українська бухгалтерська система.

Інструменти: query_bas (читання), create_bas (створення).
Список entity і допустимі операції — в описі інструменту query_bas.

Правила:
1. Одразу виклич query_bas з правильним entity_name — не шукай через metadata
2. Отримав items — форматуй відповідь, НЕ повторюй запит
3. items порожній — повідом що нічого не знайдено
4. Пошук по назві — передай параметр search

Формат відповіді — тільки нумерований список, БЕЗ таблиць (Telegram таблиці не підтримує).

Документи (кожен запис — 2 рядки):
1. №[номер] від [ДД.ММ.РРРР] — [сума] грн
   [Контрагент] · [статус якщо є]

Контрагенти (кожен запис — 2 рядки):
1. [Назва] ([код])
   [тип] · [роль] · ЄДРПОУ: [якщо є]

Порожні поля не показуй. Суми форматуй з роздільниками тисяч."""

# Tools loaded once at startup via init_tools()
_tools: list[ToolDefinition] = []


async def init_tools() -> None:
    """Load entity list from FastAPI and build tool definitions. Call once at bot startup."""
    global _tools
    entity_list = await _fetch_entity_list()
    mcp_tools = _make_tools(entity_list)
    _tools = [
        ToolDefinition(
            name=t.name,
            description=t.description,
            parameters=t.inputSchema,
        )
        for t in mcp_tools
    ]
    log.info("bot_tools_ready", tool_count=len(_tools))


async def ask(
    question: str,
    history: list[Message],
) -> tuple[str, int, int]:
    """Run agentic loop for one user question.

    Args:
        question: User's text message.
        history: Previous messages for this user (user+assistant only, no tool blocks).

    Returns:
        (answer, total_input_tokens, total_output_tokens)
    """
    client = create_llm_client()

    messages = list(history) + [Message(role="user", content=question)]

    total_input = 0
    total_output = 0

    async with httpx.AsyncClient(timeout=30.0) as http:
        for _ in range(MAX_TOOL_ITERATIONS):
            response = await client.chat_with_tools(
                messages=messages,
                tools=_tools,
                system=SYSTEM_PROMPT,
            )

            total_input += response.input_tokens
            total_output += response.output_tokens

            if not response.has_tool_calls:
                answer = response.content or "Немає відповіді."
                return answer, total_input, total_output

            # Execute all tool calls
            tool_results: list[tuple[dict, str]] = []
            for tc in response.tool_calls:
                log.info("bot_tool_call", tool=tc["name"], args=tc["arguments"])
                try:
                    result = await _dispatch(http, tc["name"], tc["arguments"])
                    result_str = json.dumps(result, ensure_ascii=False)
                except Exception as exc:
                    result_str = json.dumps({"error": str(exc)}, ensure_ascii=False)
                    log.warning("bot_tool_error", tool=tc["name"], error=str(exc))
                tool_results.append((tc, result_str))

            # Append tool_use + tool_result to messages (not to history — kept clean)
            messages.append(Message(
                role="assistant",
                content=[
                    {"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["arguments"]}
                    for tc, _ in tool_results
                ],
            ))
            messages.append(Message(
                role="user",
                content=[
                    {"type": "tool_result", "tool_use_id": tc["id"], "content": result_str}
                    for tc, result_str in tool_results
                ],
            ))

    return "Перевищено максимальну кількість ітерацій.", total_input, total_output
