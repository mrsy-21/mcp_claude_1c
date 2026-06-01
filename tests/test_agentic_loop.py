"""Integration test: full agentic loop with Groq + MCP tools + FastAPI.

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
from mcp_server.server import _dispatch

setup_logging("INFO")
log = structlog.get_logger(__name__)

FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:8000")
MAX_TOOL_ITERATIONS = 6

SYSTEM_PROMPT = """Ти — бухгалтерський асистент з доступом до 1С/BAS.
Відповідай завжди українською мовою.
Поточний рік — 2026. Якщо користувач каже "травень" — маєш на увазі 2026-05-01 по 2026-05-31.
Числа форматуй з роздільниками тисяч (наприклад: 1 234 567.00 грн).
Якщо записів більше 10 — показуй перші 10 і пиши "та ще N записів".

Система: BAS Accounting CORP 2.1 (bas-soft.eu) — українська бухгалтерська система.

Доступні інструменти:
- get_counterparties — список контрагентів, пошук по назві
- get_invoices_outgoing — рахунки на оплату покупцям, фільтр по даті (date_from/date_to у форматі РРРР-ММ-ДД)
- get_invoices_incoming — рахунки від постачальників, фільтр по даті
- get_acts — акти виконаних робіт, фільтр по даті
- create_act — створити акт
- hire_employee — оформити прийом на роботу

Правила:
1. Виклич відповідний інструмент одразу — не шукай entity через metadata
2. Якщо отримав результат з items — одразу форматуй відповідь, НЕ повторюй запит
3. Якщо items порожній — повідом що нічого не знайдено

Форматування відповіді:
- Нумерований список або таблиця
- Для документів показуй: номер, дату (ДД.ММ.РРРР), суму (грн з роздільниками), статус (Проведено/Не проведено), підставу
- Для контрагентів показуй: код, назву, тип (юр/фіз особа), ЄДРПОУ якщо є, ІПН якщо є, чи покупець, чи постачальник
- Порожні поля не показуй"""

TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        name="get_counterparties",
        description=(
            "Список контрагентів з 1С/BAS. "
            "Можна шукати по назві через параметр search."
        ),
        parameters={
            "type": "object",
            "properties": {
                "search": {"type": "string", "description": "Пошук по назві (substring)"},
                "top": {"type": "integer", "default": 50},
                "skip": {"type": "integer", "default": 0},
            },
            "required": [],
        },
    ),
    ToolDefinition(
        name="get_invoices_outgoing",
        description="Рахунки на оплату покупцям. Фільтр по даті: date_from, date_to (РРРР-ММ-ДД).",
        parameters={
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "Дата від РРРР-ММ-ДД"},
                "date_to": {"type": "string", "description": "Дата до РРРР-ММ-ДД"},
                "top": {"type": "integer", "default": 50},
                "skip": {"type": "integer", "default": 0},
            },
            "required": [],
        },
    ),
    ToolDefinition(
        name="get_invoices_incoming",
        description="Рахунки від постачальників. Фільтр по даті: date_from, date_to (РРРР-ММ-ДД).",
        parameters={
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "Дата від РРРР-ММ-ДД"},
                "date_to": {"type": "string", "description": "Дата до РРРР-ММ-ДД"},
                "top": {"type": "integer", "default": 50},
                "skip": {"type": "integer", "default": 0},
            },
            "required": [],
        },
    ),
    ToolDefinition(
        name="get_acts",
        description="Акти виконаних робіт. Фільтр по даті: date_from, date_to (РРРР-ММ-ДД).",
        parameters={
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "Дата від РРРР-ММ-ДД"},
                "date_to": {"type": "string", "description": "Дата до РРРР-ММ-ДД"},
                "top": {"type": "integer", "default": 50},
                "skip": {"type": "integer", "default": 0},
            },
            "required": [],
        },
    ),
    ToolDefinition(
        name="create_act",
        description="Створити акт виконаних робіт.",
        parameters={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Дата акту РРРР-ММ-ДД"},
                "amount": {"type": "number", "description": "Сума (грн)"},
                "basis": {"type": "string", "description": "Підстава (договір)"},
                "includes_vat": {"type": "boolean", "default": True},
            },
            "required": ["date", "amount"],
        },
    ),
    ToolDefinition(
        name="hire_employee",
        description="Оформити прийом нового співробітника на роботу.",
        parameters={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Дата прийому РРРР-ММ-ДД"},
                "employee_name": {"type": "string", "description": "ПІБ співробітника"},
                "birth_date": {"type": "string", "description": "Дата народження РРРР-ММ-ДД"},
                "position": {"type": "string", "description": "Посада"},
                "salary": {"type": "number", "description": "Оклад (грн)"},
            },
            "required": ["date", "employee_name"],
        },
    ),
]


async def run_agentic_loop(question: str) -> str:
    """Run a full agentic loop for a single user question."""
    client = create_llm_client()
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    messages: list[Message] = [Message(role="user", content=question)]

    print(f"\n{'='*60}")
    print(f"ПИТАННЯ: {question}")
    print("="*60)

    async with httpx.AsyncClient(timeout=30.0) as http:
        for _ in range(MAX_TOOL_ITERATIONS):
            response = await client.chat_with_tools(
                messages=messages,
                tools=TOOLS,
                system=SYSTEM_PROMPT,
            )

            if not response.has_tool_calls:
                print(f"\nВІДПОВІДЬ:\n{response.content}")
                return response.content or ""

            assistant_tool_calls = []

            for tc in response.tool_calls:
                print(f"\n→ Tool: {tc['name']}({json.dumps(tc['arguments'], ensure_ascii=False)[:100]})")
                try:
                    result = await _dispatch(http, tc["name"], tc["arguments"])
                    result_str = json.dumps(result, ensure_ascii=False)
                except Exception as exc:
                    result_str = json.dumps({"error": str(exc)}, ensure_ascii=False)

                # Trim to stay within Groq TPM budget
                if len(result_str) > 3500:
                    cut = result_str.rfind('}, {', 0, 3500)
                    result_str = result_str[: cut + 1] + "] [truncated]" if cut != -1 else result_str[:3500] + " [truncated]"

                preview = result_str[:150] + ("..." if len(result_str) > 150 else "")
                print(f"← Result ({len(result_str)} chars): {preview}")

                assistant_tool_calls.append((tc, result_str))

            if provider == "groq":
                messages.append(Message(
                    role="assistant",
                    content=response.content or "",
                    tool_calls=[{
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        },
                    } for tc, _ in assistant_tool_calls],
                ))
                for tc, result_str in assistant_tool_calls:
                    messages.append(Message(
                        role="tool",
                        tool_call_id=tc["id"],
                        content=result_str,
                    ))
            else:
                # Claude format
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
    print(f"Model       : {os.getenv('GROQ_MODEL', '?')}")

    if not await check_fastapi():
        print(f"\n✗ FastAPI недоступний на {FASTAPI_URL}")
        print("Запусти: uv run uvicorn api.main:app --reload")
        sys.exit(1)

    print("\n✓ FastAPI доступний")

    questions = [
        "Покажи список контрагентів (перші 5)",
        "Покажи всі рахунки на оплату за вересень 2024",
        "Знайди контрагента Синтрікс",
        "Покажи акти виконаних робіт за 2024 рік",
    ]

    for question in questions:
        try:
            await run_agentic_loop(question)
        except Exception as exc:
            print(f"\n✗ ПОМИЛКА: {exc}")
            raise

    print("\n\n✓ Всі тести завершені")


if __name__ == "__main__":
    asyncio.run(main())
