# Build from repo root: docker build -f apps/orchestrator/Dockerfile .
FROM python:slim AS orch-base
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY apps/orchestrator/requirements.txt ./
RUN pip install --no-cache-dir --default-timeout=120 \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    -r requirements.txt

FROM orch-base AS orchestrator

COPY shared/settings.py ./shared/settings.py
COPY shared/contracts ./shared/contracts
COPY shared/audit ./shared/audit
COPY apps/orchestrator/src ./src

ENV PYTHONPATH=/app/src:/app/shared
EXPOSE 8004
CMD ["uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "8004", "--no-access-log"]
