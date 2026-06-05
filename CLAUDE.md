# CLAUDE.md — Проєкт: Telegram бот з доступом до 1С через MCP + FastAPI

## Що це за проєкт

Telegram бот який дозволяє бухгалтерам запитувати дані з 1С / BAS у вільній формі.
Наприклад: "Покажи всі рахунки на оплату за травень 2026" — і бот відповідає читабельним текстом.

Під капотом: aiogram бот → Claude API → MCP server → FastAPI → 1С OData.

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
- **Назви полів entity — РОСІЙСЬКОЮ мовою** (не українською, не англійською)
- BAS не підтримує `$filter` по Date → 502. Фільтруємо в Python.
- BAS не підтримує `contains()` в `$filter` → 502. Пошук в Python.

---

## Стек

- **Python 3.11+** з **uv** (не pip)
- **aiogram 3.x** — Telegram бот (пише окремий колега)
- **Anthropic SDK** (claude-sonnet-4-6) — LLM провайдер
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
LLM абстракція (llm/)   ← Claude зараз, Groq — резервний провайдер
   ↓ tool_use / MCP
MCP сервер              ← 2 universal tools: query_bas + create_bas
   ↓ HTTP
FastAPI                 ← generic /bas/{entity_name} endpoint
   ↓ HTTP + Basic Auth
1С / BAS OData          ← джерело даних (стандартний REST інтерфейс 1С)
```

---

## Структура проєкту

```
project/
├── CLAUDE.md
├── PLAN.md               ← план рефакторингу (виконаний)
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
├── llm/                      ← LLM абстракція (Strategy + Factory)
│   ├── __init__.py
│   ├── base.py               ← абстрактний LLMClient інтерфейс
│   ├── groq_client.py        ← Groq (резерв)
│   ├── claude_client.py      ← Anthropic Claude (активний)
│   └── factory.py            ← читає LLM_PROVIDER з .env → повертає потрібний клієнт
│
├── mcp_server/
│   ├── __init__.py
│   └── server.py             ← 2 universal tools: query_bas, create_bas
│
├── api/
│   ├── __init__.py
│   ├── main.py               ← FastAPI app (підключає bas_router + metadata_router)
│   ├── schemas.py            ← мінімальні схеми (EntityQueryParams, EntityListResponse)
│   ├── odata_client.py       ← HTTP клієнт до 1С OData + clean_record()
│   └── routers/
│       ├── __init__.py
│       ├── metadata.py       ← GET /metadata (список entity, кешується)
│       └── bas.py            ← GET + POST /bas/{entity_name} (generic)
│
└── log_config/               ← НЕ logging/ — конфлікт зі stdlib Python
    ├── config.py             ← structlog налаштування
    └── grafana/
        ├── loki.yml
        └── dashboard.json
```

---

## Змінні середовища (.env)

```
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

**Щоб змінити провайдера:** тільки `LLM_PROVIDER=claude` або `LLM_PROVIDER=groq` в `.env`.

Claude використовує `input_schema` (не `parameters`) для tools.
Tool result inject: `role=user`, `content=[{type: tool_result, tool_use_id: ..., content: ...}]`.

---

## MCP Tools (2 universal tools)

| Tool | FastAPI ендпоінт | Опис |
|---|---|---|
| `query_bas` | `GET /bas/{entity_name}` | Читає будь-яку entity (Document_* або Catalog_*) |
| `create_bas` | `POST /bas/{entity_name}` | Створює запис в будь-якій entity |

**Entity list** вбудований в description кожного tool (~900 токенів замість ~37000 для повного metadata).

### Доступні entity

**ДОКУМЕНТИ:**
- `Document_СчетНаОплату` — рахунки на оплату покупцям
- `Document_СчетНаОплатуПоставщика` — рахунки від постачальників
- `Document_АктВыполненныхРабот` — акти виконаних робіт
- `Document_РасходнаяНакладная` — видаткові накладні (реалізація)
- `Document_ПриходнаяНакладная` — прибуткові накладні
- `Document_ПлатежноеПоручение` — платіжні доручення
- `Document_ПоступлениеНаСчет` — надходження на рахунок
- `Document_РасходСоСчета` — витрати з рахунку
- `Document_ПриемНаРаботу` — прийом на роботу
- `Document_Увольнение` — звільнення
- `Document_НачислениеЗарплаты` — нарахування зарплати
- `Document_ЗаказПокупателя` — замовлення покупця
- `Document_НалоговаяНакладная` — податкова накладна
- `Document_ПлатежнаяВедомость` — платіжна відомість

**ДОВІДНИКИ:**
- `Catalog_Контрагенты` — контрагенти (покупці, постачальники)
- `Catalog_Сотрудники` — співробітники
- `Catalog_Номенклатура` — номенклатура (товари, послуги)
- `Catalog_Организации` — організації
- `Catalog_Должности` — посади
- `Catalog_БанковскиеСчета` — банківські рахунки
- `Catalog_ДоговорыКонтрагентов` — договори контрагентів

### Щоб додати нову entity

1. Перевір що вона є в `/metadata` (або в `odata.xml`)
2. Додай рядок в `_ENTITY_LIST` в `mcp_server/server.py`
3. Той самий рядок — в `SYSTEM_PROMPT` в `tests/test_agentic_loop.py` і `bot/handlers.py`

---

## Ключові поведінки системи

**Python-side filtering (обхід багів BAS OData):**
- BAS не підтримує `$filter` по Date → отримуємо `$top=200`, фільтруємо в `_filter_by_date()`
- BAS не підтримує `contains()` → отримуємо всі, фільтруємо в `_filter_by_search()`
- Пошук по полях: Description, ФИО, Наименование, Number, НомерДокумента

**`clean_record()` — видаляє з OData запису:**
- DataVersion, navigationLinkUrl, Predefined*, *_Key (крім Ref_Key)
- null, "", [], epoch дати (0001-01-01T00:00:00)
- Структурні boolean: DeletionMark, IsFolder, НеАрхивный, НедействителенПоНДС

**Conversation history:**
Бот тримає history кожного користувача (по user_id) в пам'яті.
Останні 20 повідомлень передаються в кожен запит до LLM.

**Agentic loop:**
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

1. **Перед кожним новим модулем** — запитай підтвердження структури і підходу
2. **uv** — використовувати замість pip для всього Python
3. **Не додавати нових entity** без перевірки в `/metadata` або `odata.xml`
4. **Не чіпати** `api/odata_client.py` без необхідності — там обхід багів BAS
