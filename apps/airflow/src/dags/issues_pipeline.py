from datetime import datetime

from airflow import DAG  # type: ignore[reportMissingImports]
from airflow.operators.python import PythonOperator  # type: ignore[reportMissingImports]

from etl.extract import extract
from etl.normalize import normalize
from etl.llm_enrich import llm_enrich
from etl.quality_checks import quality_checks


with DAG(
    "issues_pipeline",
    start_date=datetime(2025, 1, 1),
    schedule="@daily",
    catchup=False,
) as dag:
    t1 = PythonOperator(task_id="extract_issues", python_callable=extract)
    t2 = PythonOperator(task_id="normalize_issues", python_callable=normalize)
    t3 = PythonOperator(task_id="llm_enrich", python_callable=llm_enrich)
    t4 = PythonOperator(task_id="quality_checks", python_callable=quality_checks)

    t1 >> t2 >> t3 >> t4

