# CLAUDE.md — bot/ модуль

Цей файл для розробника (і його AI агента) який працює над `bot/` модулем.

## Твоє завдання

Ти реалізуєш Telegram бот (`bot/`) який:
1. Отримує повідомлення від користувача через aiogram
2. Передає їх в agentic loop разом з history розмови
3. LLM (через `llm/`) вирішує які tools викликати
4. Результати tools повертаються назад LLM до фінальної відповіді
5. Відповідь відправляється користувачу в Telegram

## Що вже зроблено іншими

- `api/` — FastAPI сервер який спілкується з 1С OData. Запущений окремо.
- `mcp_server/` — MCP сервер з tools. Запущений окремо.
- `llm/` — абстракція над LLM (Groq зараз, Claude потім). Вже реалізована.

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
2. Відправити history + system prompt в LLM
3. Якщо відповідь містить tool_use:
   a. Викликати MCP tool
   b. Додати результат в history як tool_result
   c. Повернутись до кроку 2
4. Якщо відповідь text (end_turn) — повернути текст
```

## System prompt (використовувати цей)

```
Ти — бухгалтерський асистент з доступом до 1С/BAS.
Відповідай завжди українською мовою.
Поточний рік — 2026. Якщо користувач каже "травень" — маєш на увазі 2026-05-01 по 2026-05-31.
Результати форматуй як читабельний текст — не JSON.
Числа форматуй з роздільниками тисяч (наприклад: 1 234 567.00 грн).
Якщо записів більше 10 — показуй перші 10 і пиши "та ще N записів".
Якщо не знаєш точну назву entity 1С — спочатку виклич get_metadata.
```

## Змінні середовища (з .env)

```
TELEGRAM_BOT_TOKEN=        ← токен бота від @BotFather
GROQ_API_KEY=              ← для LLM
GROQ_MODEL=                ← moonshotai/kimi-k2-instruct
FASTAPI_URL=               ← де запущений FastAPI (http://localhost:8000)
```

## Стек

- `aiogram 3.x` — Telegram бот framework
- `python-dotenv` — .env змінні
- `structlog` — логування (JSON формат, для Grafana Loki)
- `uv` — менеджер пакетів (не pip)

## Логування

Використовуй `structlog` для всіх логів. Кожна подія — окремий лог з контекстом:

```python
import structlog
log = structlog.get_logger()

log.info("message_received", user_id=user_id, text_length=len(text))
log.info("tool_called", tool_name="get_invoices", user_id=user_id)
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
