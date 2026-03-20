# Build from repo root: docker build -f apps/mcp_server/Dockerfile .
# Two-stage: deps (cached) + app (only code). Rebuild deps only when shared/ or deps change.

# Stage deps: shared libs + heavy Python deps. No app code.
# Pre-downloads RAG embedding model so runtime never hits Hugging Face.
FROM python:3.11-slim AS deps
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        --extra-index-url https://pypi.org/simple/ \
        torch sentence-transformers qdrant-client "psycopg[binary,pool]" mcp "uvicorn[standard]"

ARG RAG_EMBEDDING_MODEL=intfloat/multilingual-e5-small
ENV HF_HOME=/app/.cache/huggingface
ENV RAG_EMBEDDING_MODEL=${RAG_EMBEDDING_MODEL}
RUN python -c "from sentence_transformers import SentenceTransformer; import os; SentenceTransformer(os.environ['RAG_EMBEDDING_MODEL'])"

# Stage app: only app source (rebuilt when apps/mcp_server/src changes).
FROM deps AS app

COPY shared/common ./shared/common
COPY shared/db ./shared/db
COPY shared/audit ./shared/audit
COPY apps/mcp_server/src ./src

RUN pip install --no-cache-dir -e ./shared/common -e ./shared/db -e ./shared/audit

ENV PYTHONPATH=/app/src
# Use pre-downloaded model only; no Hugging Face network calls at runtime.
ENV HF_HUB_OFFLINE=1
EXPOSE 8001
CMD ["uvicorn", "mcp_server.main:app", "--host", "0.0.0.0", "--port", "8001", "--no-access-log"]
