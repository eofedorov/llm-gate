# LLM-Gate

AI-шлюз для инженерных задач: классификация/извлечение по промптам и RAG по внутренней базе знаний (RFC, runbooks, ADR). Ответы только из контекста, с цитатами и статусом `insufficient_context`, если в базе нет ответа.

## Стек

- Python 3.10+
- FastAPI, Pydantic, Jinja2, OpenAI API
- RAG: Qdrant, sentence-transformers (только в образе MCP-server)
- Инфраструктура: Docker Compose (Postgres 16, Qdrant)

## Структура монорепы

- **apps/gateway** — оркестратор (FastAPI): запуск локально через uvicorn; эндпоинты `/run/*`, `/rag/*` (RAG через вызовы MCP).
- **apps/mcp_server** — MCP-сервер (tools: kb_search, kb_get_chunk, sql_read, kb_ingest); в Docker через compose.
- **apps/datastore** — хранилище документов (FastAPI): upload/read/delete; в Docker через compose; при ingest MCP-server может загружать документы с эндпоинта `/read` вместо диска.
- **shared/** — `settings.py` (базовые настройки из env), `contracts/` (Pydantic-схемы), `db/` (пул Postgres, запросы), `audit/` (клиент и middleware аудита).
- **infra/postgres** — init-скрипты БД (роли, схема `llm`).
- **data/** — база знаний (документы для RAG), монтируется в контейнер mcp-server.

## Инфраструктура

Postgres и Qdrant поднимаются через Docker Compose:

```powershell
.\scripts\dev-up.ps1
# или из корня:
docker compose -f compose.yaml up -d
```

Запускаются:

- **Postgres 16** — порт 5432, БД `llm_gate`, схема `llm` (init из `infra/postgres/`).
- **Qdrant** — порт 6333 (REST), 6334 (gRPC).
- **mcp-server** — порт 8001 (MCP tools, RAG).
- **datastore** — порт 8002 (upload/read/delete документов для RAG; при заданном `DATASTORE_URL` ingest загружает документы отсюда).

### Postgres: схема `llm`

| Таблица | Назначение |
|---|---|
| `kb_documents` | Реестр документов базы знаний |
| `kb_chunks` | Чанки документов |
| `runs` | Телеметрия запусков |
| `run_retrievals` | Аудит retrieval |
| `tool_calls` | Аудит tool-calls MCP |
| `sql_allowlist` | Allowlist для `sql_read` |

Пользователи (dev): `llm_gate_admin`, `llm_gate_service`, `llm_gate_readonly` (пароли в `infra/postgres/01_roles.sql`).

### Пересоздание с нуля

```powershell
docker compose -f compose.yaml down -v
docker compose -f compose.yaml up -d
```

## Установка и запуск

### Gateway (локально)

Из корня репозитория:

```powershell
pip install -r apps/gateway/requirements.txt
$env:PYTHONPATH = "apps/gateway/src;shared"
uvicorn gateway.main:app --reload --app-dir apps/gateway/src
```

- API: http://127.0.0.1:8000
- Документация: http://127.0.0.1:8000/docs

Для RAG-эндпоинтов нужен запущенный MCP-сервер (compose). В `.env` или `apps/gateway/dev.env` задать `MCP_SERVER_URL=http://127.0.0.1:8001` (или URL streamable HTTP MCP).

### MCP-server (Docker)

Сборка и запуск через compose (контекст — корень репо):

```powershell
docker compose -f compose.yaml up -d --build mcp-server
```

Образ собирается из `apps/mcp_server/Dockerfile`; в контейнер копируются `shared/settings.py`, `shared/contracts`, `shared/db`, `shared/audit` и код `apps/mcp_server`; `PYTHONPATH` включает `/app/shared`.

## Эндпоинты

- `GET /prompts` — список промптов и версий.
- `POST /run/{prompt_name}` — выполнить промпт (body: `version`, `task`, `input`, `constraints`).
- `POST /rag/ingest` — индексация базы знаний (через MCP tool `kb_ingest`).
- `GET /rag/search?q=...&k=5` — поиск чанков (через MCP tool `kb_search`).
- `POST /rag/ask` — ответ по контракту с цитатами (agent: MCP tools + LLM).

## Конфигурация

Переменные окружения (корневой `.env` или app-specific `dev.env`):

| Переменная | Описание |
|---|---|
| `DATABASE_URL` | Postgres (общая для mcp_server и db) |
| `QDRANT_URL`, `QDRANT_COLLECTION` | Qdrant |
| `LLM_BASE_URL`, `LLM_MODEL`, `LLM_MAX_TOKENS`, `LLM_TIMEOUT`, `LLM_MAX_RETRIES` | Gateway: LLM API |
| `MCP_SERVER_URL`, `MCP_TIMEOUT` | Gateway: MCP-сервер |
| `RAG_EMBEDDING_MODEL`, `RAG_CHUNK_SIZE`, `RAG_CHUNK_OVERLAP`, `RAG_DEFAULT_K` | MCP-server: RAG |
| `KB_PATH` | MCP-server: путь к базе знаний (в контейнере: `/app/data/docs`). Используется только если `DATASTORE_URL` не задан. |
| `DATASTORE_URL` | MCP-server: URL сервиса datastore (например `http://datastore:8002`). Если задан, при запросе **ingest** документы загружаются с эндпоинта `GET {DATASTORE_URL}/read` вместо чтения с диска по `KB_PATH`. В compose по умолчанию задаётся для mcp-server. |

## Тесты

Из корня репозитория установить зависимости приложения (`pip install -r apps/<app>/requirements.txt`), затем запускать pytest с `PYTHONPATH`, включающим `shared` и `apps/<app>/src`.
