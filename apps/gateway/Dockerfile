# Optional: build from repo root: docker build -f apps/gateway/Dockerfile .
# Gateway normally runs locally via uvicorn.
FROM python:slim
WORKDIR /app
COPY shared/common ./shared/common
COPY shared/audit ./shared/audit
COPY apps/gateway/src ./src
RUN pip install --no-cache-dir -e ./shared/common -e ./shared/audit \
    && pip install --no-cache-dir fastapi "uvicorn[standard]" pydantic pydantic-settings jinja2 openai tiktoken mcp httpx
ENV PYTHONPATH=/app/src
EXPOSE 8000
CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
