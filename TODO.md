# TODO — Порядок розробки

## Крок 1 — Структура проєкту ✅
- [x] Папки: bot/, llm/, mcp_server/, api/routers/, log_config/grafana/
- [x] pyproject.toml (uv)
- [x] .env.example
- [x] .gitignore
- [x] CLAUDE.md (кореневий)
- [x] bot/CLAUDE.md (для колеги)

## Крок 2 — FastAPI + OData клієнт ✅
- [x] api/main.py — FastAPI app, lifespan, structlog
- [x] api/odata_client.py — httpx клієнт з Basic Auth, GET/POST, fetch_metadata
- [x] api/routers/metadata.py — GET /metadata (кеш) + POST /metadata/refresh
- [x] log_config/config.py — structlog setup (console / JSON для Loki)

## Крок 3 — Універсальний роутер ✅
- [x] api/schemas.py — Pydantic схеми (EntityQueryParams, EntityListResponse, EntityCreateResponse)
- [x] api/routers/entity.py — GET /entity/{entity_name} + POST /entity/{entity_name}
- [ ] Тест через Swagger з реальними entity з тестової бази

## Крок 4 — MCP сервер
- [ ] mcp_server/server.py — два tools:
  - `query_entity` — GET /entity/{name} з фільтрами
  - `create_entity` — POST /entity/{name} з body
  - `get_metadata` — GET /metadata

## Крок 5 — LLM абстракція ✅
- [x] llm/base.py — LLMClient (ABC), Message, ToolDefinition, LLMResponse
- [x] llm/groq_client.py — Groq / Kimi K2 реалізація
- [x] llm/claude_client.py — Claude реалізація (готова, чекає API key)
- [x] llm/factory.py — Strategy + Factory, LLM_PROVIDER з .env

## Крок 6 — Agentic loop + бот
- [ ] bot/history.py — in-memory history по user_id (макс 20 повідомлень)
- [ ] bot/claude_client.py — agentic loop (tool_use цикл)
- [ ] bot/handlers.py — /start, /clear, /help, text handler
- [ ] bot/main.py — точка входу, polling

## Крок 7 — Логування
- [ ] Підключити structlog в api/, bot/, llm/
- [ ] Зареєструватись на Grafana Cloud, отримати Loki URL + credentials
- [ ] log_config/grafana/loki.yml — конфіг
- [ ] log_config/grafana/dashboard.json — базовий dashboard

## Крок 8 — Docker
- [ ] Dockerfile для api/
- [ ] Dockerfile для bot/ + mcp_server/
- [ ] docker-compose.yml — підняти все одною командою

## Крок 9 — CI/CD
- [ ] .github/workflows/ci.yml — lint + tests
- [ ] .github/workflows/deploy.yml — build + push Docker image

## Крок 10 — Міграція на Claude API
- [ ] llm/claude_client.py — повна реалізація
- [ ] Перевірити agentic loop з Claude
- [ ] Оновити .env.example, документацію
