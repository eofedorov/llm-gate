# Build from repo root: docker build -f apps/orchestrator/Dockerfile .
FROM python:slim AS orch-base
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl nodejs npm \
    && rm -rf /var/lib/apt/lists/*

COPY apps/orchestrator/requirements.txt ./
RUN pip install --no-cache-dir --default-timeout=120 \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    -r requirements.txt

FROM orch-base AS orchestrator

COPY apps/orchestrator/cursor_agent_cli/package*.json ./cursor_agent_cli/
RUN cd cursor_agent_cli && npm ci

COPY apps/orchestrator/cursor_agent_cli/tsconfig.json ./cursor_agent_cli/tsconfig.json
COPY apps/orchestrator/cursor_agent_cli/src ./cursor_agent_cli/src
RUN cd cursor_agent_cli && npm run build && npm prune --omit=dev

COPY shared/settings.py ./shared/settings.py
COPY shared/contracts ./shared/contracts
COPY shared/audit ./shared/audit
COPY apps/orchestrator/src ./src

ENV PYTHONPATH=/app/src:/app/shared
EXPOSE 8004
CMD ["uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "8004", "--no-access-log"]
