"""MCP server — exposes 1C/BAS data as tools for LLM consumption.

Runs as a stdio MCP process. The LLM calls these tools during the agentic
loop; each tool makes an HTTP request to the FastAPI service.

Tools (generated dynamically at startup):
    query_bas   — читає будь-яку entity з BAS (список entity з $metadata)
    create_bas  — створює запис в BAS для заданої entity

Як в odata_mcp_go --universal:
  При старті тягне GET /metadata з FastAPI, фільтрує по BAS_ENTITY_WHITELIST,
  генерує _ENTITY_LIST у форматі "EntityName [ops]" і вбудовує в description tool.
  Якщо BAS_ENTITY_WHITELIST порожній — використовує всі entity.

Start with:
    uv run python -m mcp_server.server
"""

import asyncio
import fnmatch
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

# Whitelist: comma-separated entity names, supports fnmatch wildcards (* ?)
# Empty = use all entities from $metadata
_WHITELIST_RAW = os.getenv("BAS_ENTITY_WHITELIST", "")

server = Server("bas-odata-mcp")

# Ops по типу entity — як в Go: Catalog підтримує search, Document — ні
_CATALOG_OPS = "list,get,count,search"
_DOCUMENT_OPS = "list,get,count"
# Entities що підтримують create
_CREATABLE = frozenset({
    "Document_АктВыполненныхРабот",
    "Document_ПриемНаРаботу",
})


def _parse_whitelist(raw: str) -> list[str]:
    """Парсить BAS_ENTITY_WHITELIST — список через кому, прибирає пробіли."""
    if not raw.strip():
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def _matches_whitelist(name: str, patterns: list[str]) -> bool:
    """Перевіряє чи entity name відповідає хоча б одному pattern (fnmatch)."""
    if not patterns:
        return True  # порожній whitelist = всі
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def _entity_ops(name: str) -> str:
    """Повертає рядок операцій для entity — як в Go [list,get,count,search]."""
    if name.startswith("Catalog_"):
        ops = _CATALOG_OPS
    else:
        ops = _DOCUMENT_OPS
    if name in _CREATABLE:
        ops += ",create"
    return ops


def _build_entity_list(entities: list[dict]) -> str:
    """Будує _ENTITY_LIST рядок з списку entity — як generateUniversalDescription() в Go."""
    patterns = _parse_whitelist(_WHITELIST_RAW)
    lines = []
    for e in sorted(entities, key=lambda x: x["name"]):
        name = e["name"]
        if not _matches_whitelist(name, patterns):
            continue
        ops = _entity_ops(name)
        lines.append(f"{name} [{ops}]")
    return "\n".join(lines)


async def _fetch_entity_list() -> str:
    """Тягне /metadata з FastAPI і будує entity list.

    Якщо FastAPI недоступний — повертає порожній рядок і логує warning.
    MCP server все одно стартує, але tools будуть з порожнім описом entity.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{FASTAPI_URL}/metadata")
            r.raise_for_status()
            data = r.json()
            entities = data.get("entities", [])
            entity_list = _build_entity_list(entities)
            log.info(
                "mcp_entity_list_built",
                total_from_metadata=len(entities),
                after_whitelist=entity_list.count("\n") + 1 if entity_list else 0,
            )
            return entity_list
    except Exception as exc:
        log.warning("mcp_metadata_fetch_failed", error=str(exc))
        return ""


def _make_tools(entity_list: str) -> list[Tool]:
    """Генерує список MCP tools з динамічним entity_list в description."""
    query_description = (
        "Читає дані з 1С/BAS. Параметр entity_name — обов'язковий.\n\n"
        "Entities:\n"
        + (entity_list if entity_list else "(metadata unavailable — check FastAPI)")
        + "\n\nОперації: list=список, get=один запис, count=кількість, search=пошук по назві."
    )

    create_description = (
        "Створює новий запис в 1С/BAS.\n\n"
        "Entities з підтримкою create:\n"
        + "\n".join(
            f"  {name}"
            for name in sorted(_CREATABLE)
        )
    )

    return [
        Tool(
            name="query_bas",
            description=query_description,
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Назва entity зі списку вище",
                    },
                    "date_from": {
                        "type": "string",
                        "description": "Дата від РРРР-ММ-ДД (для Document_*)",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "Дата до РРРР-ММ-ДД (для Document_*)",
                    },
                    "search": {
                        "type": "string",
                        "description": "Пошук по назві/ПІБ (для Catalog_* з [search])",
                    },
                    "top": {
                        "type": "integer",
                        "default": 20,
                        "description": "Кількість записів (default 20, макс 200)",
                    },
                    "skip": {
                        "type": "integer",
                        "default": 0,
                        "description": "Пропустити перші N (пагінація)",
                    },
                },
                "required": ["entity_name"],
            },
        ),
        Tool(
            name="create_bas",
            description=create_description,
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Назва entity",
                    },
                    "data": {
                        "type": "object",
                        "description": "Поля запису (ключі — назви полів BAS)",
                    },
                },
                "required": ["entity_name", "data"],
            },
        ),
    ]


# Буде заповнено при старті в main()
_tools: list[Tool] = []


@server.list_tools()
async def list_tools() -> list[Tool]:
    return _tools


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
            log.warning("mcp_tool_http_error", tool=name, status=exc.response.status_code)
            return [TextContent(type="text", text=json.dumps(error, ensure_ascii=False))]
        except httpx.RequestError as exc:
            error = {"error": "FastAPI unreachable", "detail": str(exc)}
            log.error("mcp_tool_request_error", tool=name, error=str(exc))
            return [TextContent(type="text", text=json.dumps(error, ensure_ascii=False))]

    log.info("mcp_tool_done", tool=name)
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def _dispatch(client: httpx.AsyncClient, name: str, args: dict) -> dict:
    if name == "query_bas":
        entity_name = args["entity_name"]
        params = {
            k: args[k]
            for k in ("date_from", "date_to", "search", "top", "skip")
            if k in args
        }
        r = await client.get(f"{FASTAPI_URL}/bas/{entity_name}", params=params)
        r.raise_for_status()
        return r.json()

    if name == "create_bas":
        entity_name = args["entity_name"]
        data = args.get("data", {})
        r = await client.post(f"{FASTAPI_URL}/bas/{entity_name}", json=data)
        r.raise_for_status()
        return r.json()

    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    global _tools

    log.info("mcp_server_starting", fastapi_url=FASTAPI_URL)

    # Динамічно будуємо entity list з $metadata — як в Go при старті
    entity_list = await _fetch_entity_list()
    _tools = _make_tools(entity_list)

    log.info("mcp_tools_ready", tool_count=len(_tools))

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
