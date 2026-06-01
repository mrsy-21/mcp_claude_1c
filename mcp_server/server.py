"""MCP server — exposes 1C/BAS data as tools for LLM consumption.

Runs as a stdio MCP process. The LLM calls these tools during the agentic
loop; each tool makes an HTTP request to the FastAPI service.

Tools:
    get_counterparties       — список контрагентів
    get_invoices_outgoing    — рахунки на оплату покупцям
    get_invoices_incoming    — рахунки від постачальників
    get_acts                 — акти виконаних робіт
    create_act               — створити акт
    hire_employee            — оформити прийом на роботу

Start with:
    uv run python -m mcp_server.server
"""

import asyncio
import json
import os

import httpx
import structlog
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

load_dotenv()

from log_config.config import setup_logging

setup_logging(os.getenv("LOG_LEVEL", "INFO"))

log = structlog.get_logger(__name__)

FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:8000")

server = Server("bas-odata-mcp")


_TOOLS: list[Tool] = [
    Tool(
        name="get_counterparties",
        description=(
            "Повертає список контрагентів з 1С/BAS (Catalog_Контрагенты). "
            "Можна шукати по назві. "
            "Повертає: ref, code, name, type (ЮридическоеЛицо/ФизическоеЛицо), "
            "edrpou (ЄДРПОУ), inn (ІПН), is_buyer, is_supplier."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "search": {
                    "type": "string",
                    "description": "Пошук по назві контрагента (substring). Наприклад: 'Синтрікс'",
                },
                "top": {
                    "type": "integer",
                    "default": 50,
                    "description": "Кількість записів (макс 200)",
                },
                "skip": {"type": "integer", "default": 0},
            },
            "required": [],
        },
    ),
    Tool(
        name="get_invoices_outgoing",
        description=(
            "Рахунки на оплату покупцям (Document_СчетНаОплату). "
            "Повертає: ref, number, date, posted, amount (СуммаДокумента), "
            "includes_vat, payment_type, basis (договір)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "date_from": {
                    "type": "string",
                    "description": "Дата від у форматі РРРР-ММ-ДД",
                },
                "date_to": {
                    "type": "string",
                    "description": "Дата до у форматі РРРР-ММ-ДД",
                },
                "top": {"type": "integer", "default": 50},
                "skip": {"type": "integer", "default": 0},
            },
            "required": [],
        },
    ),
    Tool(
        name="get_invoices_incoming",
        description=(
            "Рахунки на оплату від постачальників (Document_СчетНаОплатуПоставщика). "
            "Повертає: ref, number, date, posted, amount, includes_vat, payment_type, basis."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "date_from": {
                    "type": "string",
                    "description": "Дата від у форматі РРРР-ММ-ДД",
                },
                "date_to": {
                    "type": "string",
                    "description": "Дата до у форматі РРРР-ММ-ДД",
                },
                "top": {"type": "integer", "default": 50},
                "skip": {"type": "integer", "default": 0},
            },
            "required": [],
        },
    ),
    Tool(
        name="get_acts",
        description=(
            "Акти виконаних робіт (Document_АктВыполненныхРабот). "
            "Повертає: ref, number, date, posted, amount, includes_vat, basis."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "date_from": {
                    "type": "string",
                    "description": "Дата від у форматі РРРР-ММ-ДД",
                },
                "date_to": {
                    "type": "string",
                    "description": "Дата до у форматі РРРР-ММ-ДД",
                },
                "top": {"type": "integer", "default": 50},
                "skip": {"type": "integer", "default": 0},
            },
            "required": [],
        },
    ),
    Tool(
        name="create_act",
        description="Створити акт виконаних робіт (Document_АктВыполненныхРабот).",
        inputSchema={
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Дата акту у форматі РРРР-ММ-ДД",
                },
                "amount": {"type": "number", "description": "Сума документа (грн)"},
                "basis": {"type": "string", "description": "Підстава (назва договору)"},
                "includes_vat": {"type": "boolean", "default": True},
            },
            "required": ["date", "amount"],
        },
    ),
    Tool(
        name="hire_employee",
        description="Оформити прийом нового співробітника на роботу (Document_ПриемНаРаботу).",
        inputSchema={
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Дата прийому у форматі РРРР-ММ-ДД",
                },
                "employee_name": {"type": "string", "description": "ПІБ співробітника"},
                "birth_date": {
                    "type": "string",
                    "description": "Дата народження РРРР-ММ-ДД",
                },
                "position": {"type": "string", "description": "Посада"},
                "salary": {"type": "number", "description": "Оклад (грн)"},
            },
            "required": ["date", "employee_name"],
        },
    ),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return _TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    log.info("mcp_tool_call", tool=name, args=arguments)

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            result = await _dispatch(client, name, arguments)
        except httpx.HTTPStatusError as exc:
            error = {
                "error": f"FastAPI returned {exc.response.status_code}",
                "detail": exc.response.text,
            }
            log.warning(
                "mcp_tool_http_error", tool=name, status=exc.response.status_code
            )
            return [
                TextContent(type="text", text=json.dumps(error, ensure_ascii=False))
            ]
        except httpx.RequestError as exc:
            error = {"error": "FastAPI unreachable", "detail": str(exc)}
            log.error("mcp_tool_request_error", tool=name, error=str(exc))
            return [
                TextContent(type="text", text=json.dumps(error, ensure_ascii=False))
            ]

    log.info("mcp_tool_done", tool=name)
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def _dispatch(client: httpx.AsyncClient, name: str, args: dict) -> dict:
    """Route tool call to the correct FastAPI endpoint."""

    if name == "get_counterparties":
        params = {k: args[k] for k in ("search", "top", "skip") if k in args}
        r = await client.get(f"{FASTAPI_URL}/counterparties", params=params)
        r.raise_for_status()
        return r.json()

    if name == "get_invoices_outgoing":
        params = {
            k: args[k] for k in ("date_from", "date_to", "top", "skip") if k in args
        }
        r = await client.get(f"{FASTAPI_URL}/invoices/outgoing", params=params)
        r.raise_for_status()
        return r.json()

    if name == "get_invoices_incoming":
        params = {
            k: args[k] for k in ("date_from", "date_to", "top", "skip") if k in args
        }
        r = await client.get(f"{FASTAPI_URL}/invoices/incoming", params=params)
        r.raise_for_status()
        return r.json()

    if name == "get_acts":
        params = {
            k: args[k] for k in ("date_from", "date_to", "top", "skip") if k in args
        }
        r = await client.get(f"{FASTAPI_URL}/acts", params=params)
        r.raise_for_status()
        return r.json()

    if name == "create_act":
        r = await client.post(f"{FASTAPI_URL}/acts", json=args)
        r.raise_for_status()
        return r.json()

    if name == "hire_employee":
        r = await client.post(f"{FASTAPI_URL}/hr/hire", json=args)
        r.raise_for_status()
        return r.json()

    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    log.info("mcp_server_starting", fastapi_url=FASTAPI_URL)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
