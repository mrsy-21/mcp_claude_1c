# CLAUDE.md — Проєкт: Telegram бот з доступом до 1С через MCP + FastAPI

## Що це за проєкт

Telegram бот який дозволяє бухгалтерам запитувати дані з 1С / BAS у вільній формі.
Наприклад: "Покажи всі рахунки на оплату за травень 2026" — і бот відповідає читабельним текстом.

Під капотом: aiogram бот → Claude API → MCP server → FastAPI → 1С OData.

Приклади запитів:
- «Покажи всі рахунки на оплату за травень 2026»
- «Знайди контрагента Синтрикс і покажи його останні 5 документів реалізації»
- «Який оборот по рахунку 311 за останній місяць?»
- «Створи акт для Синтрікса на суму 100к грн за послуги "консультація з ІТ" для ТОВ Гудвіл»
- «Беремо на роботу Спірідонова Павла 02.02.1988 на посаду Супер бухгалтер з зп 15000грн. Оформи.»

---

## 1С / BAS система

**BAS Accounting CORP, edition 2.1 (2.1.33.4)**
- Розробник: NetHelp JAROCKI PIOTR / bas-soft.eu
- OData інтерфейс стандартний (як у 1С), але назви entity можуть відрізнятись від типової 1С
- **Назви полів entity — РОСІЙСЬКОЮ мовою** (не українською, не англійською)
- BAS не підтримує `$filter` по Date → 502. Фільтруємо в Python.
- BAS не підтримує `contains()` в `$filter` → 502. Пошук в Python.
- `Catalog_*` не має поля `Date` → `$orderby=Date desc` тільки для `Document_*`

---

## Стек

- **Python 3.12** з **uv** (не pip)
- **aiogram 3.x** — Telegram бот (пише окремий колега)
- **Anthropic SDK** (claude-sonnet-4-6) — LLM провайдер
- **MCP Python SDK** — MCP сервер (stdio)
- **FastAPI + uvicorn** — бізнес-логіка і запити до 1С
- **httpx** — HTTP клієнт для запитів до 1С OData
- **structlog** — структуроване JSON логування
- **Docker + Loki + Promtail + Grafana** — моніторинг стек

---

## Архітектура (чотири шари)

```
Telegram
   ↓
aiogram бот             ← отримує повідомлення, тримає history розмови
   ↓
LLM абстракція (llm/)   ← Claude зараз, Groq — резервний провайдер
   ↓ tool_use / MCP
MCP сервер              ← 2 universal tools: query_bas + create_bas
   ↓ HTTP
FastAPI (Docker :8001)  ← generic /bas/{entity_name} endpoint
   ↓ HTTP + Basic Auth
1С / BAS OData          ← джерело даних (стандартний REST інтерфейс 1С)
```

---

## Структура проєкту

```
mcp_claude_1c/
├── CLAUDE.md
├── PLAN.md               ← план рефакторингу (виконаний)
├── TODO.md               ← статус задач
├── .env / .env.example
├── pyproject.toml        ← uv, не pip/requirements.txt
├── docker-compose.yml    ← FastAPI + Loki + Promtail + Grafana
│
├── bot/                  ← пише окремий колега, ще не реалізовано
│   ├── main.py
│   ├── handlers.py
│   ├── claude_client.py  ← agentic loop
│   └── history.py        ← history по user_id
│
├── llm/                  ← LLM абстракція (Strategy + Factory)
│   ├── base.py           ← LLMClient (ABC), LLMResponse (input/output tokens)
│   ├── groq_client.py    ← Groq (резерв)
│   ├── claude_client.py  ← Anthropic Claude (активний)
│   └── factory.py        ← LLM_PROVIDER з .env
│
├── mcp_server/
│   └── server.py         ← 2 universal tools + динамічний entity list
│
├── api/
│   ├── main.py           ← FastAPI app
│   ├── schemas.py        ← EntityQueryParams, EntityListResponse
│   ├── odata_client.py   ← httpx клієнт + clean_record()
│   └── routers/
│       ├── metadata.py   ← GET /metadata (кешується)
│       └── bas.py        ← GET + POST /bas/{entity_name}
│
├── log_config/
│   └── config.py         ← structlog JSON (RotatingFileHandler) + httpx заглушений
│
├── docker/
│   ├── Dockerfile        ← образ FastAPI
│   ├── loki-config.yml
│   ├── promtail-config.yml
│   └── grafana/
│       └── provisioning/
│           ├── datasources/loki.yml
│           └── dashboards/
│               ├── dashboard.yml
│               └── bas-mcp.json  ← 6 панелей (Log Stream, Errors, Tokens, Tools, Rate, Error Rate)
│
├── logs/                 ← app.log читається Promtail (shared volume)
└── tests/
    └── test_agentic_loop.py  ← інтеграційний тест з Claude
```

---

## Як запустити

### Docker стек (FastAPI + моніторинг)
```bash
docker-compose up --build -d
```
- FastAPI: http://localhost:8001
- Grafana: http://localhost:3000 (admin/admin)
- Loki: http://localhost:3100

> **Важливо:** FastAPI в Docker не може звертатись до BAS OData по локальному IP.
> MCP сервер запускається локально і звертається до FastAPI через localhost:8001.
> Entity list завантажується MCP сервером при старті з GET /metadata.

### Локальний запуск FastAPI (для розробки)
```bash
uv run uvicorn api.main:app --reload --port 8000
```

### MCP сервер (запускається з Claude Desktop або bot/)
```bash
uv run python -m mcp_server.server
```

### Тести
```bash
# FastAPI має бути запущений (локально або Docker :8001)
uv run python tests/test_agentic_loop.py
```

---

## Змінні середовища (.env)

```env
# Telegram
TELEGRAM_BOT_TOKEN=

# LLM
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-4-6

# Groq (резерв, не активний)
# GROQ_API_KEY=
# GROQ_MODEL=openai/gpt-oss-120b

# 1С OData
ODATA_BASE_URL=http://IP/BaseName/odata/standard.odata
ODATA_USER=
ODATA_PASSWORD=

# FastAPI (в Docker FastAPI слухає :8000, зовні :8001)
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8000
FASTAPI_URL=http://localhost:8001

# Логування
LOG_FORMAT=json          # json → файл + stdout; console → кольоровий stdout
LOG_LEVEL=INFO
LOG_DIR=logs             # папка де Promtail читає app.log

# Whitelist entity (через кому, підтримує wildcard *)
# Якщо порожньо — всі entity з $metadata
BAS_ENTITY_WHITELIST=Document_СчетНаОплату,...
```

---

## Моніторинг (Docker Loki + Grafana)

### Потік логів
```
FastAPI (structlog JSON) → logs/app.log
                                ↓ (shared volume)
                          Promtail → парсить JSON, витягує level/event labels
                                ↓
                            Loki (зберігає)
                                ↓
                          Grafana (dashboard)
```

### Grafana Dashboard "BAS MCP Monitor"
URL: http://localhost:3000/d/bas-mcp-001

| Панель | Query | Опис |
|--------|-------|------|
| Log Stream | `{service="bas-mcp"}` | Всі логи live |
| Errors & Warnings | `level=~"error\|warning"` | Тільки помилки |
| Input Tokens per Request | `unwrap input_tokens` на `event="claude_response"` | Токени Claude |
| Tool Calls | `count_over_time event="mcp_tool_call"` | Виклики інструментів |
| Tool Call Rate | останній 1h barchart | Топ інструментів |
| Error Rate | `level="error"` і `level="warning"` по часу | Динаміка помилок |

### Важливо: datasource UID
Grafana datasource UID прописаний хардкодом в `docker/grafana/dashboards/bas-mcp.json`: `P8E80F9AEF21F6940`.
Якщо дашборд не показує дані після чистого старту:
```bash
# Скинути позицію Promtail і перезапустити
docker exec promtail rm /var/log/promtail-positions.yaml
docker restart promtail
```

---

## LLM абстракція (Strategy + Factory)

**Щоб змінити провайдера:** тільки `LLM_PROVIDER=claude` або `LLM_PROVIDER=groq` в `.env`.

Claude використовує `input_schema` (не `parameters`) для tools.
Tool result inject: `role=user`, `content=[{type: tool_result, tool_use_id: ..., content: ...}]`.
`LLMResponse` містить `input_tokens` і `output_tokens` для моніторингу витрат.

---

## MCP Tools (2 universal tools)

| Tool | FastAPI ендпоінт | Опис |
|---|---|---|
| `query_bas` | `GET /bas/{entity_name}` | Читає будь-яку entity (Document_* або Catalog_*) |
| `create_bas` | `POST /bas/{entity_name}` | Створює запис в будь-якій entity |

**Entity list** генерується динамічно при старті MCP сервера з `GET /metadata` FastAPI.
Формат: `EntityName [ops]` (наприклад `Document_АктВыполненныхРабот [list,get,count,create]`).
Фільтрується через `BAS_ENTITY_WHITELIST` в `.env` (fnmatch wildcards підтримуються).

### Щоб додати нову entity

1. Переконайся що вона є в `GET /metadata` (або `/metadata/search?q=назва`)
2. Додай в `BAS_ENTITY_WHITELIST` в `.env`
3. Перезапусти MCP сервер (він завантажує entity list при старті)

---

## Ключові поведінки системи

### Python-side filtering (обхід багів BAS OData)
- BAS не підтримує `$filter` по Date → отримуємо `$top=200`, фільтруємо в `_filter_by_date()`
- BAS не підтримує `contains()` → отримуємо всі, фільтруємо в `_filter_by_search()`
- Пошук по полях: Description, ФИО, Наименование, Number, НомерДокумента

### `clean_record()` — видаляє з OData запису
- `__metadata`, `DataVersion`, navigationLinkUrl
- Поля `*_Key` (крім Ref_Key), Predefined*
- null, "", [] (порожні значення)
- Epoch дати (0001-01-01T00:00:00)
- Структурні boolean: DeletionMark, IsFolder, НеАрхивный, НедействителенПоНДС

### `_apply_size_limits()` — обмеження відповіді
- MAX_ITEMS = 50 записів
- MAX_RESPONSE_BYTES = 15 KB
- Відповідь не містить `truncated` або `original_count` — щоб LLM не намагався робити пагінацію

### Conversation history
Бот тримає history кожного користувача (по user_id) в пам'яті.
Останні 20 повідомлень передаються в кожен запит до LLM.

### Agentic loop
Claude може викликати кілька tools підряд.
Цикл: Claude відповідає tool_use → MCP викликає FastAPI → результат повертається Claude → до end_turn.

---

## System prompt для LLM (актуальний)

```
Ти — бухгалтерський асистент з доступом до 1С/BAS.
Відповідай завжди українською мовою.
Поточний рік — 2026. Якщо користувач каже "травень" — маєш на увазі 2026-05-01 по 2026-05-31.
Числа форматуй з роздільниками тисяч (наприклад: 1 234 567.00 грн).
Якщо записів більше 10 — показуй перші 10 і пиши "та ще N записів".

Система: BAS Accounting CORP 2.1 (bas-soft.eu) — українська бухгалтерська система.

Доступні інструменти:
- query_bas — єдиний інструмент для читання даних з BAS.
  Параметри: entity_name (обов'язково), date_from, date_to (РРРР-ММ-ДД), search, top, skip.
- create_bas — створити запис в BAS.

Список доступних entity вбудований в опис інструменту query_bas.
Не вигадуй назв entity — використовуй тільки зі списку.

Правила:
1. Для будь-якого читання даних — одразу виклич query_bas з правильним entity_name
2. Якщо отримав результат з items — одразу форматуй відповідь, НЕ повторюй запит
3. Якщо items порожній — повідом що нічого не знайдено
4. Для пошуку по назві — передай параметр search

Форматування відповіді:
- Нумерований список або таблиця
- Для документів: номер, дату (ДД.ММ.РРРР), суму (грн з роздільниками), статус
- Для контрагентів: код, назву, тип, ЄДРПОУ якщо є, ІПН якщо є
- Порожні поля не показуй
```

---

## Як працювати з цим проєктом (інструкція для Claude)

1. **uv** — використовувати замість pip для всього Python
2. **Не чіпати** `api/odata_client.py` без необхідності — там обхід багів BAS
3. **Не додавати нових entity хардкодом** — тільки через `BAS_ENTITY_WHITELIST` в `.env`
4. **LOG_FORMAT=json** в `.env` — обов'язково для Docker/Loki/Grafana
5. **Тести** запускати тільки коли FastAPI доступний (localhost:8001 або :8000)
