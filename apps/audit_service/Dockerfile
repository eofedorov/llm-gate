# Build from repo root: docker build -f apps/audit_service/Dockerfile .
FROM python:slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY apps/audit_service/src ./src
COPY apps/audit_service/requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/data

ENV PYTHONPATH=/app/src
ENV AUDIT_DB_PATH=/app/data/audit.db
EXPOSE 8003
CMD ["uvicorn", "audit_service.main:app", "--host", "0.0.0.0", "--port", "8003", "--no-access-log"]
