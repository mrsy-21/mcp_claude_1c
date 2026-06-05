# План рефакторингу: Universal Tool + міграція на Claude

## Що робимо

1. Мігруємо LLM з Groq на Claude API
2. Замінюємо 6 hardcoded tools на 1 universal tool `query_bas`
3. FastAPI отримує generic endpoint який вміє обходити баги BAS

---

## Крок 1 — Міграція на Claude API

**Файли:**
- `.env` — змінити `LLM_PROVIDER=claude`, переконатись що `ANTHROPIC_API_KEY` є
- `llm/claude_client.py` — перевірити і виправити якщо треба
- `llm/factory.py` — переконатись що `claude` provider зареєстрований

**Перевірити:**
- `claude_client.py` використовує `anthropic` SDK (не openai-compatible)
- Tool format: `input_schema` замість `parameters`
- Tool result inject: `role=user`, `content=[{type: tool_result, ...}]`
- Model: `claude-sonnet-4-6` (поточна)

---

## Крок 2 — Generic FastAPI endpoint

Зараз є 4 окремих роутери. Замінюємо на один `GET /bas/{entity_name}` який:
- Приймає `date_from`, `date_to`, `search`, `top`, `skip`
- Фільтрує по даті в Python (обхід бага BAS з `$filter`)
- Фільтрує по `search` в Python (обхід бага BAS з `contains()`)
- Повертає очищені записи через `clean_record()`
- **Не має Pydantic response схем** — повертає `{"count": N, "items": [...]}`

**Файли:**
- `api/routers/bas.py` — новий generic router
- `api/main.py` — підключити `bas_router`, прибрати старі роутери
- `api/routers/counterparties.py`, `invoices.py`, `acts.py`, `hr.py` — **видалити**
- `api/schemas.py` — прибрати конкретні Pydantic моделі, залишити тільки `EntityQueryParams`

**Логіка фільтрації в `bas.py`:**
```
1. Завжди fetch $top=200 без $filter від OData
2. Python-side: фільтр по Date якщо є date_from/date_to
3. Python-side: фільтр по Description/ФИО якщо є search
4. Повернути items[skip:skip+top]
```

---

## Крок 3 — Universal MCP tool

Замінюємо 6 tools на 2:

### Tool 1: `query_bas`
```
Читає дані з 1С/BAS. Параметри:
- entity_name: назва entity (обов'язково)
- date_from, date_to: фільтр по даті (РРРР-ММ-ДД)
- search: пошук по назві/ПІБ
- top: кількість записів (default 20)
- skip: пагінація
```

**В description вбудувати curated список entity:**
```
Доступні entity (Document_* — документи, Catalog_* — довідники):

ДОКУМЕНТИ:
Document_СчетНаОплату — рахунки на оплату покупцям
Document_СчетНаОплатуПоставщика — рахунки від постачальників
Document_АктВыполненныхРабот — акти виконаних робіт
Document_РасходнаяНакладная — видаткові накладні (реалізація)
Document_ПриходнаяНакладная — прибуткові накладні
Document_ПлатежноеПоручение — платіжні доручення
Document_ПоступлениеНаСчет — надходження на рахунок
Document_РасходСоСчета — витрати з рахунку
Document_ПриемНаРаботу — прийом на роботу
Document_Увольнение — звільнення
Document_НачислениеЗарплаты — нарахування зарплати
Document_ЗаказПокупателя — замовлення покупця
Document_НалоговаяНакладная — податкова накладна
Document_ПлатежнаяВедомость — платіжна відомість

ДОВІДНИКИ:
Catalog_Контрагенты — контрагенти (покупці, постачальники)
Catalog_Сотрудники — співробітники
Catalog_Номенклатура — номенклатура (товари, послуги)
Catalog_Организации — організації
Catalog_Должности — посади
Catalog_БанковскиеСчета — банківські рахунки
Catalog_ДоговорыКонтрагентов — договори контрагентів
```

### Tool 2: `create_bas`
```
Створює запис в 1С/BAS. Параметри:
- entity_name: назва entity
- data: dict з полями запису
```

**Файли:**
- `mcp_server/server.py` — переписати повністю, 2 tools замість 6
- `tests/test_agentic_loop.py` — оновити TOOLS і system prompt

---

## Крок 4 — System prompt

Оновити system prompt для Claude:
- Прибрати інструкції про `search_metadata` (більше не потрібно)
- Додати що `query_bas` — єдиний інструмент для читання
- Додати правило: якщо entity не знаєш — дивись список в описі tool
- Формат дати для фільтрів: `РРРР-ММ-ДД`
- Формат відповіді: таблиця з датою, номером, сумою, контрагентом

---

## Крок 5 — Оновити документацію

- `CLAUDE.md` — оновити system prompt і архітектуру
- `bot/CLAUDE.md` — оновити список tools для колеги

---

## Що НЕ чіпаємо

- `api/odata_client.py` — залишається як є
- `api/routers/metadata.py` — залишається (для майбутніх баз)
- `llm/base.py`, `llm/groq_client.py`, `llm/factory.py` — залишаються
- `log_config/` — залишається
- `tests/test_llm.py` — залишається

---

## Порядок виконання

1. Крок 1 (Claude) — 15 хв
2. Крок 2 (generic endpoint) — 30 хв
3. Крок 3 (universal tool) — 20 хв
4. Крок 4 (system prompt) — 10 хв
5. Крок 5 (документація) — 10 хв
6. Тест — запустити `test_agentic_loop.py` на всіх питаннях

**Загалом: ~1.5 години**
