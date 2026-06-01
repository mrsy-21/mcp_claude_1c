# CLAUDE.md — Проєкт: Telegram бот з доступом до 1С через MCP + FastAPI

## Що це за проєкт

Telegram бот який дозволяє бухгалтерам запитувати дані з 1С / BAS у вільній формі.
Наприклад: "Покажи всі рахунки на оплату за травень 2026" — і бот відповідає читабельним текстом.

Під капотом: aiogram бот → LLM (Groq/Claude) через абстракцію → FastAPI → 1С OData.

Приклади запитів які має обробляти бот:
- «Покажи всі рахунки на оплату за травень 2026»
- «Знайди контрагента Синтрикс і покажи його останні 5 документів реалізації»
- «Який оборот по рахунку 311 за останній місяць?»
- «Створи акт для Синтрікса на суму 100к грн за послуги "консультація з ІТ" для ТОВ Гудвіл»
- «Покажи всі акти по компанії Синтрікс»
- «Беремо на роботу нового співробітника Спірідонова Павла 02.02.1988 на посаду Супер бухгалтер з зп 15000грн. Оформи його в систему»

---

## 1С / BAS система

**BAS Accounting CORP, edition 2.1 (2.1.33.4)**
- Розробник: NetHelp JAROCKI PIOTR
- Сайт: https://www.bas-soft.eu/soft/bas-mass/bas-accounting-korp/
- OData інтерфейс стандартний (як у 1С), але назви entity можуть відрізнятись від типової 1С:Бухгалтерії
- При дебазі назв entity і структури запитів — документація на bas-soft.eu

---

## Стек

- **Python 3.11+** з **uv** (не pip)
- **aiogram 3.x** — Telegram бот
- **Groq SDK** (Kimi K2) → потім мігруємо на **Anthropic SDK** (Claude)
- **MCP Python SDK** — MCP сервер з tools
- **FastAPI + uvicorn** — бізнес-логіка і запити до 1С
- **httpx** — HTTP клієнт для запитів до 1С OData
- **structlog** — структуроване логування (JSON, для Grafana Loki)
- **python-dotenv** — змінні середовища

---

## Архітектура (чотири шари)

```
Telegram
   ↓
aiogram бот             ← отримує повідомлення, тримає history розмови
   ↓
LLM абстракція (llm/)   ← Groq зараз, Claude потім — swap без змін в боті
   ↓ tool_use / MCP
MCP сервер              ← перетворює tool_use виклик на HTTP запит
   ↓ HTTP
FastAPI                 ← бізнес-логіка, формує OData запити до 1С
   ↓ HTTP + Basic Auth
1С / BAS OData          ← джерело даних (стандартний REST інтерфейс 1С)
```

---

## Структура проєкту

```
project/
├── CLAUDE.md
├── .env.example
├── pyproject.toml            ← uv, не pip/requirements.txt
├── uv.lock
├── docker-compose.yml
│
├── bot/
│   ├── __init__.py
│   ├── main.py               ← точка входу бота
│   ├── handlers.py           ← aiogram handlers
│   ├── claude_client.py      ← agentic loop, використовує llm/
│   └── history.py            ← history по user_id (останні 20 повідомлень)
│
├── llm/                      ← LLM абстракція (окремо від бота)
│   ├── __init__.py
│   ├── base.py               ← абстрактний LLMClient інтерфейс
│   ├── groq_client.py        ← Kimi K2 реалізація
│   └── claude_client.py      ← Claude реалізація (потім)
│
├── mcp_server/
│   ├── __init__.py
│   └── server.py             ← MCP tools (описи + виклики FastAPI)
│
├── api/
│   ├── __init__.py
│   ├── main.py               ← FastAPI app
│   ├── odata_client.py       ← HTTP клієнт до 1С OData + кеш metadata
│   └── routers/
│       ├── __init__.py
│       ├── metadata.py       ← GET /metadata (список entity, кешується)
│       ├── invoices.py       ← GET /invoices/outgoing, /invoices/incoming
│       ├── payments.py       ← GET /payments
│       ├── counterparties.py ← GET /counterparties
│       ├── acts.py           ← GET + POST /acts
│       └── hr.py             ← POST /employees
│
└── log_config/               ← НЕ logging/ — конфлікт зі stdlib Python
    ├── config.py             ← structlog налаштування
    └── grafana/
        ├── loki.yml          ← Loki конфіг
        └── dashboard.json    ← Grafana dashboard
```

---

## Змінні середовища (.env)

```
# Telegram
TELEGRAM_BOT_TOKEN=

# LLM (Groq зараз)
GROQ_API_KEY=
GROQ_MODEL=moonshotai/kimi-k2-instruct

# Anthropic (потім)
# ANTHROPIC_API_KEY=
# ANTHROPIC_MODEL=claude-sonnet-4-20250514

# 1С OData
ODATA_BASE_URL=http://IP/BaseName/odata/standard.odata
ODATA_USER=
ODATA_PASSWORD=

# FastAPI
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8000
FASTAPI_URL=http://localhost:8000

# Grafana / Loki
LOKI_URL=https://logs-prod-XXX.grafana.net/loki/api/v1/push
LOKI_USER=
LOKI_API_KEY=
```

---

## LLM абстракція (Strategy + Factory)

```
llm/
├── base.py          ← LLMClient (ABC), Message, ToolDefinition, LLMResponse
├── groq_client.py   ← Groq / Kimi K2 (OpenAI-сумісний формат)
├── claude_client.py ← Anthropic Claude (інший формат tool_use)
└── factory.py       ← читає LLM_PROVIDER з .env → повертає потрібний клієнт
```

**Щоб змінити провайдера:** тільки `LLM_PROVIDER=claude` в `.env` — більше нічого.

**Щоб додати нового провайдера:**
1. Створити `llm/<provider>_client.py` — наслідувати `LLMClient`
2. Додати запис в `_PROVIDERS` у `factory.py`
3. Змінити `LLM_PROVIDER` в `.env`

Бот і MCP сервер імпортують тільки `factory.create_llm_client()` — не знають про конкретний провайдер.

---

## MCP Tools

| Tool | FastAPI ендпоінт | Коли викликається |
|---|---|---|
| `get_invoices_outgoing` | `GET /invoices/outgoing` | рахунки покупцям |
| `get_invoices_incoming` | `GET /invoices/incoming` | рахунки від постачальників |
| `get_payments` | `GET /payments` | платежі, оплати |
| `get_counterparties` | `GET /counterparties` | пошук контрагентів |
| `get_acts` | `GET /acts` | акти виконаних робіт |
| `create_act` | `POST /acts` | створення акту |
| `get_account_turnovers` | `GET /account-turnovers` | обороти по рахунку бухобліку |
| `create_employee` | `POST /employees` | оформлення нового співробітника |
| `get_metadata` | `GET /metadata` | список entity (коли LLM не знає назву) |

> ⚠️ Список може змінюватись. Перед додаванням нового tool — запитай.

---

## Ключові поведінки системи

**Conversation history:**
Бот тримає history кожного користувача (по user_id) в пам'яті процесу.
Останні 20 повідомлень передаються в кожен запит до LLM.
Команда /clear — очищає history.

**Agentic loop:**
LLM може викликати кілька tools підряд в одному запиті.
Цикл: LLM відповідає tool_use → MCP викликає FastAPI → результат повертається LLM → повторюємо до end_turn.

**Metadata кеш:**
При старті FastAPI викликає `GET $metadata` до 1С OData і кешує список entity.
LLM може запитати `/metadata` щоб дізнатись точні назви entity перед запитом.

**Форматування відповідей:**
LLM відповідає українською мовою.
Числа форматуються з роздільниками тисяч.
Якщо записів більше 10 — показуємо перші 10 і пишемо "та ще N записів".
Довгі відповіді розбиваємо на частини (ліміт Telegram 4096 символів).

**Обробка помилок:**
Помилки OData (404, 401, 500) перехоплюються у FastAPI і повертаються як зрозумілий текст.
LLM пояснює помилку користувачу простою мовою.

**Логування:**
structlog пише JSON логи.
Кожен запит до LLM, кожен tool_use виклик і кожна відповідь від OData логується.
Логи відправляються в Grafana Loki (Grafana Cloud, безкоштовний tier).

---

## System prompt для LLM

```
Ти — бухгалтерський асистент з доступом до 1С/BAS.
Відповідай завжди українською мовою.
Поточний рік — 2026. Якщо користувач каже "травень" — маєш на увазі 2026-05-01 по 2026-05-31.
Числа форматуй з роздільниками тисяч (наприклад: 1 234 567.00 грн).
Якщо записів більше 10 — показуй перші 10 і пиши "та ще N записів".

Система: BAS Accounting CORP 2.1 (bas-soft.eu) — українська бухгалтерська система.
Назви полів entity — російською мовою. Важливо:
- Ідентифікаційний код (ЄДРПОУ) — поле КодПоЕДРПОУ (не КПП, не ИНН)
- ІПН фізособи — поле ИНН
- Назва контрагента — поле Description
- Вид контрагента — поле ВидКонтрагента (значення: ЮридическоеЛицо, ФизическоеЛицо)
- Дата документу — поле Дата
- Сума документу — поле СуммаДокумента

Для пошуку даних:
1. Якщо не знаєш точну назву entity — виклич search_metadata з назвою документа УКРАЇНСЬКОЮ або РОСІЙСЬКОЮ мовою
   Приклади: search_metadata("рахунок") → знайде Document_РахунокНаОплату; search_metadata("акт") → Document_АктВыполненныхРабот
2. Отримай точну назву entity і виклич query_entity без select — завжди отримуй всі поля
3. Не використовуй select — це може призвести до помилок якщо поле не існує
4. Для фільтрації по даті використовуй OData формат: Дата ge datetime'2026-05-01T00:00:00' and Дата le datetime'2026-05-31T23:59:59'

Форматування відповіді:
- Нумерований список або таблиця
- Для документів показуй: номер, дату (ДД.ММ.РРРР), суму (грн з роздільниками), статус (Проведено/Не проведено), підставу
- Для контрагентів показуй: код, назву, тип (юр/фіз особа), ЄДРПОУ якщо є, ІПН якщо є, чи покупець, чи постачальник
- Порожні поля не показуй

Важливо про виклик інструментів:
- Якщо інструмент повернув дані (навіть якщо count=0) — одразу формуй відповідь, НЕ повторюй той самий запит
- Якщо отримав помилку — повідом користувача і не повторюй запит
```

---

## Оцінка часу

| Фаза | Опис | Час |
|---|---|---|
| 1 | Структура + pyproject.toml + .env.example | 0.5 дня |
| 2 | FastAPI + odata_client + перший роутер (metadata + invoices) | 1-2 дні |
| 3 | MCP сервер + перший tool | 1 день |
| 4 | LLM абстракція + agentic loop | 1-2 дні |
| 5 | aiogram бот + history | 1 день |
| 6 | Решта роутерів (payments, counterparties, acts, hr) | 2-3 дні |
| 7 | structlog + Grafana Loki | 1-2 дні |
| 8 | CI/CD (GitHub Actions) | 1 день |
| 9 | Тестування + міграція на Claude API | 1-2 дні |
| **Разом** | | **9-14 робочих днів** |

---

## Як працювати з цим проєктом (інструкція для Claude)

1. **Перед кожним новим модулем** — запитай підтвердження структури і підходу
2. **Перед написанням коду** — опиши словами що збираєшся зробити
3. **Якщо є кілька варіантів реалізації** — запропонуй їх і поясни різницю
4. **Не пиши весь проєкт одразу** — рухайся крок за кроком
5. **Якщо щось не зрозуміло** — питай, не вигадуй
6. **uv** — використовувати замість pip для всього Python

## Порядок розробки

1. ✅ Структура проєкту обговорена
2. ⬜ Створити папки + pyproject.toml + .env.example
3. ⬜ FastAPI + odata_client.py + metadata роутер
4. ⬜ Invoices роутер + тест через Swagger
5. ⬜ MCP сервер з першим tool
6. ⬜ LLM абстракція (base + groq)
7. ⬜ Agentic loop + aiogram handlers + history
8. ⬜ Решта роутерів і tools
9. ⬜ structlog + Grafana Loki
10. ⬜ docker-compose
11. ⬜ CI/CD
12. ⬜ Міграція на Claude API
