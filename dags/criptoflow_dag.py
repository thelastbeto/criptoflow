from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from bronze import executar as executar_bronze

def alerta_falha(context):
    ti = context["task_instance"]
    print(
        f"🚨 ALERTA: a task '{ti.task_id}' falhou no DAG '{ti.dag_id}' "
        f"(run {context['run_id']}). Confira os logs."
    )

with DAG(
    dag_id="criptoflow_medallion",
    schedule="@hourly",              # de hora em hora (o cron, mas gerenciado)
    start_date=datetime(2026, 1, 1),
    catchup=False,                   # não reprocessa o passado ao ligar
    tags=["criptoflow"],
    dagrun_timeout=timedelta(hours=1),          # o run inteiro não passa de 1h
    default_args={
        "on_failure_callback": alerta_falha,
        "retries": 3,                            # tenta 3x antes de falhar de vez
        "retry_delay": timedelta(minutes=2),     # espera 2min entre tentativas
        "retry_exponential_backoff": True,       # 2 → 4 → 8min (dá tempo do 429 passar)
        "execution_timeout": timedelta(minutes=15),  # mata a TASK travada em 15min
    },
) as dag:

    t_bronze = PythonOperator(
        task_id="bronze",
        python_callable=executar_bronze,          # ingestão: CoinGecko -> MinIO
    )

    t_dbt = BashOperator(
        task_id="dbt_build",
        bash_command=(
            "dbt build "
            "--project-dir /opt/airflow/project/criptoflow_dbt "
            "--profiles-dir /home/airflow/.dbt"
        ),                                         # transformação: staging + marts + testes
    )

    t_bronze >> t_dbt

    