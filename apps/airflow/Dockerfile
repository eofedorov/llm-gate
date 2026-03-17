# Build from repo root: docker build -f apps/airflow/Dockerfile .
FROM apache/airflow:3.1.8-python3.11

USER root
WORKDIR /opt/airflow

COPY apps/airflow/src/dags ./dags
COPY apps/airflow/src/etl ./etl


ENV PYTHONPATH=/opt/airflow/etl

USER airflow

