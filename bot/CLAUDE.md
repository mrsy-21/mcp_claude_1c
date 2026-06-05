# CLAUDE.md — bot/ модуль

Цей файл для розробника (і його AI агента) який працює над `bot/` модулем.

## Твоє завдання

Ти реалізуєш Telegram бот (`bot/`) який:
1. Отримує повідомлення від користувача через aiogram
2. Передає їх в agentic loop разом з history розмови
3. Claude (через `llm/`) вирішує які tools викликати
4. Результати tools повертаються назад Claude до фінальної відповіді
5. Відповідь відправляється користувачу в Telegram

## Що вже зроблено іншими

- `api/` — FastAPI сервер який спілкується з 1С OData. Запущений окремо.
- `mcp_server/` — MCP сервер з 2 universal tools. Запущений окремо.
- `llm/` — абстракція над LLM (Claude зараз). Вже реалізована.

**Тобі не потрібно чіпати ці модулі.**

## Архітектура bot/

```
bot/
├── main.py          ← запуск: ініціалізує бота, підключає handlers, стартує polling
├── handlers.py      ← aiogram message handlers (текст, /start, /clear, /help)
├── claude_client.py ← agentic loop: history + LLM + tool_use цикл
└── history.py       ← in-memory history по user_id (dict[int, list[Message]])
```

## Ключові деталі реалізації

### history.py
- Зберігає history в пам'яті: `dict[user_id: int, messages: list]`
- Максимум **20 останніх повідомлень** на користувача
- Метод `clear(user_id)` — очищає history для /clear команди
- При перевищенні 20 — видаляємо найстаріші (не system prompt)

### handlers.py
- `/start` — привітання + що вміє бот
- `/clear` — очищає history, підтверджує користувачу
- `/help` — список команд
- Звичайне повідомлення → передати в `claude_client.py` → відправити відповідь
- Довгі відповіді (>4096 символів) розбивати на частини

### claude_client.py (agentic loop)
```
1. Додати повідомлення користувача в history
2. Відправити history + system prompt в Claude
3. Якщо відповідь містить tool_use:
   a. Викликати MCP tool через _dispatch()
   b. Додати результат в history як tool_result
      format: role=user, content=[{type: tool_result, tool_use_id: ..., content: ...}]
   c. Повернутись до кроку 2
4. Якщо відповідь text (end_turn) — повернути текст
```

**Важливо для Claude message format:**
- Tool calls у відповіді assistant: `content=[{type: tool_use, id: ..., name: ..., input: {...}}]`
- Tool results у відповіді user: `content=[{type: tool_result, tool_use_id: ..., content: "..."}]`

## MCP Tools (2 universal tools)

```python
TOOLS = [
    ToolDefinition(
        name="query_bas",
        description="Читає дані з 1С/BAS. entity_name обов'язковий...",
        parameters={
            "type": "object",
            "properties": {
                "entity_name": {"type": "string"},   # обов'язково
                "date_from": {"type": "string"},      # РРРР-ММ-ДД
                "date_to": {"type": "string"},        # РРРР-ММ-ДД
                "search": {"type": "string"},
                "top": {"type": "integer", "default": 20},
                "skip": {"type": "integer", "default": 0},
            },
            "required": ["entity_name"],
        },
    ),
    ToolDefinition(
        name="create_bas",
        description="Створює запис в 1С/BAS.",
        parameters={
            "type": "object",
            "properties": {
                "entity_name": {"type": "string"},
                "data": {"type": "object"},
            },
            "required": ["entity_name", "data"],
        },
    ),
]
```

Повний список entity і їх описи — в `mcp_server/server.py` (константа `_ENTITY_LIST`).
Скопіюй той же список в system prompt бота.

## System prompt (використовувати цей)

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

## Змінні середовища (з .env)

```
TELEGRAM_BOT_TOKEN=        ← токен бота від @BotFather
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-4-6
FASTAPI_URL=               ← де запущений FastAPI (http://localhost:8000)
```

## Стек

- `aiogram 3.x` — Telegram бот framework
- `python-dotenv` — .env змінні
- `structlog` — логування (JSON формат, для Grafana Loki)
- `uv` — менеджер пакетів (не pip)

## Логування

```python
import structlog
log = structlog.get_logger()

log.info("message_received", user_id=user_id, text_length=len(text))
log.info("tool_called", tool_name="query_bas", entity="Document_СчетНаОплату", user_id=user_id)
log.info("response_sent", user_id=user_id, response_length=len(response))
log.error("llm_error", user_id=user_id, error=str(e))
```

## Що НЕ робити

- Не підключатись до 1С напряму — тільки через MCP tools
- Не писати бізнес-логіку в handlers — handlers тільки routing
- Не зберігати history в файл/БД — тільки in-memory (поки що)
- Не форматувати відповіді як JSON — тільки читабельний текст

## Як запустити (після налаштування .env)

```bash
uv run python -m bot.main
```
