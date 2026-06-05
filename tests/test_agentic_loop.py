"""Integration test: full agentic loop with Claude + universal MCP tools + FastAPI.

Simulates the real bot flow without Telegram:
  user question → LLM → tool calls → FastAPI/1C → LLM → final answer

FastAPI must be running at FASTAPI_URL before executing this test.

Run with:
    uv run python -m tests.test_agentic_loop
"""

import asyncio
import json
import os
import sys

import httpx
import structlog
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from log_config.config import setup_logging
from llm.factory import create_llm_client
from llm.base import Message, ToolDefinition
from mcp_server.server import _dispatch, _fetch_entity_list, _make_tools

setup_logging("INFO")
log = structlog.get_logger(__name__)

FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:8000")
MAX_TOOL_ITERATIONS = 8

SYSTEM_PROMPT = """Ти — бухгалтерський асистент з доступом до 1С/BAS.
Відповідай завжди українською мовою.
Поточний рік — 2026. Якщо користувач каже "травень" — маєш на увазі 2026-05-01 по 2026-05-31.
Числа форматуй з роздільниками тисяч (наприклад: 1 234 567.00 грн).

Система: BAS Accounting CORP 2.1 (bas-soft.eu) — українська бухгалтерська система.

Інструменти: query_bas (читання), create_bas (створення).
Список entity і допустимі операції — в описі інструменту query_bas.

Правила:
1. Одразу виклич query_bas з правильним entity_name — не шукай через metadata
2. Отримав items — форматуй відповідь, НЕ повторюй запит
3. items порожній — повідом що нічого не знайдено
4. Пошук по назві — передай параметр search

Формат відповіді: таблиця. Документи: номер, дата (ДД.ММ.РРРР), сума (грн), статус.
Контрагенти: код, назва, тип, ЄДРПОУ/ІПН якщо є. Порожні поля не показуй."""


def _mcp_tools_to_tool_definitions(mcp_tools) -> list[ToolDefinition]:
    """Конвертує MCP Tool об'єкти в ToolDefinition для LLM клієнта."""
    return [
        ToolDefinition(
            name=t.name,
            description=t.description,
            parameters=t.inputSchema,
        )
        for t in mcp_tools
    ]


async def run_agentic_loop(question: str, tools: list[ToolDefinition]) -> str:
    """Run a full agentic loop for a single user question."""
    client = create_llm_client()
    messages: list[Message] = [Message(role="user", content=question)]

    total_input = 0
    total_output = 0

    print(f"\n{'='*60}")
    print(f"ПИТАННЯ: {question}")
    print("="*60)

    async with httpx.AsyncClient(timeout=30.0) as http:
        for _ in range(MAX_TOOL_ITERATIONS):
            response = await client.chat_with_tools(
                messages=messages,
                tools=tools,
                system=SYSTEM_PROMPT,
            )

            total_input += response.input_tokens
            total_output += response.output_tokens
            print(f"  [tokens] in={response.input_tokens} out={response.output_tokens} "
                  f"(total in={total_input} out={total_output})")

            if not response.has_tool_calls:
                print(f"\nВІДПОВІДЬ:\n{response.content}")
                print(f"\n[ПІДСУМОК ТОКЕНІВ] input={total_input} output={total_output} "
                      f"total={total_input + total_output}")
                return response.content or ""

            assistant_tool_calls = []

            for tc in response.tool_calls:
                print(f"\n→ Tool: {tc['name']}({json.dumps(tc['arguments'], ensure_ascii=False)[:120]})")
                try:
                    result = await _dispatch(http, tc["name"], tc["arguments"])
                    result_str = json.dumps(result, ensure_ascii=False)
                except Exception as exc:
                    result_str = json.dumps({"error": str(exc)}, ensure_ascii=False)

                preview = result_str[:200] + ("..." if len(result_str) > 200 else "")
                print(f"← Result ({len(result_str)} chars): {preview}")

                assistant_tool_calls.append((tc, result_str))

            messages.append(Message(
                role="assistant",
                content=[{
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["arguments"],
                } for tc, _ in assistant_tool_calls],
            ))
            messages.append(Message(
                role="user",
                content=[{
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": result_str,
                } for tc, result_str in assistant_tool_calls],
            ))

    return "Перевищено максимальну кількість ітерацій."


async def check_fastapi() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{FASTAPI_URL}/health")
            return r.status_code == 200
    except Exception:
        return False


async def main() -> None:
    print(f"FastAPI URL : {FASTAPI_URL}")
    print(f"LLM provider: {os.getenv('LLM_PROVIDER', 'groq')}")
    print(f"Model       : {os.getenv('ANTHROPIC_MODEL', os.getenv('GROQ_MODEL', '?'))}")

    if not await check_fastapi():
        print(f"\n✗ FastAPI недоступний на {FASTAPI_URL}")
        print("Запусти: uv run uvicorn api.main:app --reload")
        sys.exit(1)

    print("\n✓ FastAPI доступний")

    # Динамічно тягнемо entity list — як MCP server при реальному запуску
    print("Завантажую entity list з /metadata...")
    entity_list = await _fetch_entity_list()
    mcp_tools = _make_tools(entity_list)
    tools = _mcp_tools_to_tool_definitions(mcp_tools)

    # Показуємо що згенерувалось
    print(f"Entity list ({entity_list.count(chr(10)) + 1} entities):")
    for line in entity_list.splitlines():
        print(f"  {line}")
    print()

    questions = [
        "Покажи список контрагентів (перші 5)",
        "Покажи всі рахунки на оплату за вересень 2024",
        # "Знайди контрагента Синтрікс",
        # "Покажи акти виконаних робіт за 2024 рік",
        # "Покажи видаткові накладні за грудень 2024",
        # "Знайди співробітника Іваненко",
    ]

    for question in questions:
        try:
            await run_agentic_loop(question, tools)
        except Exception as exc:
            print(f"\n✗ ПОМИЛКА: {exc}")
            raise

    print("\n\n✓ Всі тести завершені")


if __name__ == "__main__":
    asyncio.run(main())
