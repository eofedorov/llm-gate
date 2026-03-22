# Build from repo root: docker build -f apps/airflow/Dockerfile .
FROM apache/airflow:3.1.8-python3.11

USER root
WORKDIR /opt/airflow

COPY apps/airflow/src/dags ./dags
COPY apps/airflow/src/etl ./etl

# Метаданные: postgresql+psycopg:// в compose. psycopg2 из базового образа снимаем (pip как команда root запрещён — только python -m pip).
RUN python -m pip install --no-cache-dir "psycopg[binary]" \
    && (python -m pip uninstall -y psycopg2-binary || true) \
    && (python -m pip uninstall -y psycopg2 || true)

ENV PYTHONPATH=/opt/airflow

USER airflow
