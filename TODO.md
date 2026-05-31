# TODO — Порядок розробки

## Крок 1 — Структура проєкту
- [x] Папки: bot/, llm/, mcp_server/, api/routers/, logging/grafana/
- [x] pyproject.toml (uv)
- [x] .env.example
- [x] .gitignore
- [x] CLAUDE.md (кореневий)
- [x] bot/CLAUDE.md (для колеги)

## Крок 2 — FastAPI skeleton + OData клієнт
- [ ] api/main.py — FastAPI app, CORS, startup event
- [ ] api/odata_client.py — httpx клієнт з Basic Auth, GET/POST методи
- [ ] api/routers/metadata.py — GET /metadata (запит $metadata до 1С, кеш)
- [ ] api/routers/invoices.py — GET /invoices/outgoing, GET /invoices/incoming

## Крок 3 — Тест FastAPI
- [ ] Перевірити /metadata через Swagger (http://localhost:8000/docs)
- [ ] Перевірити /invoices через Swagger або curl

## Крок 4 — MCP сервер
- [ ] mcp_server/server.py — MCP tools: get_metadata, get_invoices_outgoing, get_invoices_incoming

## Крок 5 — LLM абстракція
- [ ] llm/base.py — абстрактний клас LLMClient
- [ ] llm/groq_client.py — реалізація через Groq (Kimi K2)
- [ ] llm/claude_client.py — заглушка / реалізація (при міграції)

## Крок 6 — Agentic loop + бот
- [ ] bot/history.py — in-memory history по user_id (макс 20 повідомлень)
- [ ] bot/claude_client.py — agentic loop (tool_use цикл)
- [ ] bot/handlers.py — /start, /clear, /help, text handler
- [ ] bot/main.py — точка входу, polling

## Крок 7 — Решта роутерів і tools
- [ ] api/routers/payments.py + MCP tool get_payments
- [ ] api/routers/counterparties.py + MCP tool get_counterparties
- [ ] api/routers/acts.py (GET + POST) + MCP tools get_acts, create_act
- [ ] api/routers/hr.py (POST) + MCP tool create_employee
- [ ] api/routers/account_turnovers.py + MCP tool get_account_turnovers

## Крок 8 — Логування
- [ ] logging/config.py — structlog налаштування (JSON, Grafana Loki)
- [ ] Підключити логування в api/, bot/, llm/
- [ ] Зареєструватись на Grafana Cloud, отримати Loki URL + credentials
- [ ] logging/grafana/loki.yml — конфіг
- [ ] logging/grafana/dashboard.json — базовий dashboard

## Крок 9 — Docker
- [ ] Dockerfile для api/
- [ ] Dockerfile для bot/ + mcp_server/
- [ ] docker-compose.yml — підняти все одною командою

## Крок 10 — CI/CD
- [ ] .github/workflows/ci.yml — lint + tests
- [ ] .github/workflows/deploy.yml — build + push Docker image

## Крок 11 — Міграція на Claude API
- [ ] llm/claude_client.py — повна реалізація
- [ ] Перевірити agentic loop з Claude
- [ ] Оновити .env.example, документацію
