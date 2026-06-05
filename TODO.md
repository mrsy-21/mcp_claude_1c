# TODO — Порядок розробки

## ✅ Зроблено

### Інфраструктура
- [x] Структура проєкту: bot/, llm/, mcp_server/, api/, log_config/, docker/
- [x] pyproject.toml (uv), .env, .env.example, .gitignore
- [x] CLAUDE.md, bot/CLAUDE.md

### FastAPI + OData
- [x] api/odata_client.py — httpx клієнт з Basic Auth, clean_record()
- [x] api/routers/metadata.py — GET /metadata + /metadata/index + /metadata/search
- [x] api/routers/bas.py — generic GET/POST /bas/{entity_name} з Python-side фільтрацією
- [x] api/main.py — FastAPI app, lifespan

### LLM абстракція
- [x] llm/base.py — LLMClient (ABC), Message, ToolDefinition, LLMResponse (з input/output tokens)
- [x] llm/groq_client.py — Groq резервний провайдер
- [x] llm/claude_client.py — Anthropic Claude (активний)
- [x] llm/factory.py — Strategy + Factory, LLM_PROVIDER з .env

### MCP сервер
- [x] mcp_server/server.py — 2 universal tools: query_bas + create_bas
- [x] Динамічна генерація entity list з GET /metadata при старті (як в odata_mcp_go)
- [x] BAS_ENTITY_WHITELIST в .env — фільтр entity з підтримкою wildcards

### Оптимізація токенів
- [x] Entity list у форматі "EntityName [ops]" замість розгорнутих описів (~1400 токенів)
- [x] _apply_size_limits() — MAX_ITEMS=50, MAX_RESPONSE_BYTES=15KB
- [x] Прибрано truncated/original_count з відповіді (не провокує пагінацію)
- [x] $orderby=Date desc тільки для Document_* (Catalog_ не має поля Date)

### Моніторинг
- [x] log_config/config.py — structlog JSON в файл (RotatingFileHandler) + заглушено httpx логи
- [x] docker-compose.yml — FastAPI + Loki + Promtail + Grafana
- [x] docker/Dockerfile — образ для FastAPI
- [x] docker/loki-config.yml, promtail-config.yml
- [x] docker/grafana/ — provisioning datasource + dashboard
- [x] Dashboard: Log Stream, Errors & Warnings, Token Usage, Tool Calls, Error Rate

### Тести
- [x] tests/test_agentic_loop.py — повний agentic loop тест з Claude
- [x] Динамічне завантаження entity list перед тестом
- [x] Відображення токенів per request і total

---

## ⬜ В роботі / Наступне

### Бот (пише окремий колега)
- [ ] bot/history.py — in-memory history по user_id (макс 20 повідомлень)
- [ ] bot/claude_client.py — agentic loop (tool_use цикл з Claude format)
- [ ] bot/handlers.py — /start, /clear, /help, text handler
- [ ] bot/main.py — точка входу, polling
- [ ] Тест з реальним Telegram

### Оптимізація токенів
- [ ] Дослідити які поля BAS реально використовує Claude у відповідях
- [ ] Можливо: slim_record() для конкретних entity (залишати тільки топ-5 полів)

### CI/CD
- [ ] .github/workflows/ci.yml — lint + tests
- [ ] .github/workflows/deploy.yml — build + push Docker image

### Майбутнє
- [ ] AccountingRegister — оборот по рахунку 311 (складніший запит)
- [ ] Додати нові entity в whitelist якщо з'являться нові питання
