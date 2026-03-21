# Build from repo root: docker build -f apps/orchestrator/Dockerfile .
FROM python:slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY shared/common ./shared/common
COPY shared/audit ./shared/audit
COPY apps/orchestrator/src ./src
COPY apps/orchestrator/requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH=/app/src
EXPOSE 8004
CMD ["uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "8004", "--no-access-log"]
