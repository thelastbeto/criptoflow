from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator

from bronze import executar as executar_bronze
from silver import executar as executar_silver
from gold   import executar as executar_gold

with DAG(
    dag_id="criptoflow_medallion",
    schedule="@hourly",              # de hora em hora (o cron, mas gerenciado)
    start_date=datetime(2026, 1, 1),
    catchup=False,                   # não reprocessa o passado ao ligar
    tags=["criptoflow"],
) as dag:

    t_bronze = PythonOperator(task_id="bronze", python_callable=executar_bronze)
    t_silver = PythonOperator(task_id="silver", python_callable=executar_silver)
    t_gold   = PythonOperator(task_id="gold",   python_callable=executar_gold)

    t_bronze >> t_silver >> t_gold   # a ordem/dependência

    