# LLM-Gate

AI-шлюз для инженерных задач: классификация/извлечение по промптам и RAG по внутренней базе знаний (RFC, runbooks, ADR). Ответы только из контекста, с цитатами и статусом `insufficient_context`, если в базе нет ответа.

## Стек

- Python 3.10+
- FastAPI, Pydantic, Jinja2, OpenAI API
- RAG: FAISS, sentence-transformers
- Сборка: hatchling

## Установка

```powershell
pip install -e ".[dev]"
```

Из корня репозитория. Для тестов с индексацией и golden set нужны `faiss-cpu` и `sentence-transformers` (уже в зависимостях).

## Запуск

Из корня репозитория (после `pip install -e .`):

```powershell
uvicorn app.main:app --reload
```

Либо с явным путём к приложению:

```powershell
$env:PYTHONPATH = "src"
uvicorn app.main:app --reload --app-dir src
```

- API: http://127.0.0.1:8000  
- Документация: http://127.0.0.1:8000/docs  

## Эндпоинты

### Промпты (классификация / извлечение)

- `GET /prompts` — список промптов и версий
- `POST /run/{prompt_name}` — выполнить промпт (body: `version`, `task`, `input`, `constraints`)

Пример:

```powershell
curl -X POST http://127.0.0.1:8000/run/classify -H "Content-Type: application/json" -d '{\"version\": \"v1\", \"task\": \"Classify\", \"input\": \"После релиза 2.1.3 на странице оплаты 500 ошибка.\"}'
```

### RAG (база знаний)

- `POST /rag/ingest` — индексация документов из `data/knowledge_base.json` в FAISS (ответ: `docs_indexed`, `chunks_indexed`, `duration_ms`)
- `GET /rag/search?q=...&k=5` — поиск чанков по запросу
- `POST /rag/ask` — ответ по контракту с цитатами (body: `question`, `k`, `filters?`, `strict_mode`)

Перед поиском и ответами нужно один раз вызвать `POST /rag/ingest`.

## Конфигурация

Переменные окружения (или `.env`): настройки LLM (`llm_base_url`, `llm_model`, `llm_max_tokens`, `llm_timeout`, `llm_max_retries`), опционально `rag_index_dir` для пути к индексу FAISS (по умолчанию `data/faiss_index/`).

## Тесты

```powershell
pytest
```

Из корня репозитория; `pythonpath` и `testpaths` заданы в `pyproject.toml`. Медленные тесты (ingest + retrieval): `pytest -m "not slow"` — без них.
