import os
import duckdb
from dotenv import load_dotenv

# --- Config do MinIO (porta 9100 = API S3, a que remapeamos) ---
load_dotenv()

MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT')
MINIO_KEY      = os.getenv('MINIO_KEY')
MINIO_SECRET   = os.getenv('MINIO_SECRET')


con = duckdb.connect()

con.execute('INSTALL httpfs; LOAD httpfs;')
con.execute(f"SET s3_endpoint='localhost:9100';")
con.execute(f"SET s3_access_key_id={MINIO_KEY};")
con.execute(f"SET s3_secret_access_key={MINIO_SECRET};")
con.execute("SET s3_use_ssl=false;")
con.execute("SET s3_url_style='path';")
con.execute("SET s3_region='us-east-1';")

FCT = "read_parquet('s3://criptoflow/gold/fct_precos/fct_precos.parquet')"
DIM = "read_parquet('s3://criptoflow/gold/dim_moeda/dim_moeda.parquet')"

consulta = f"""
SELECT
    d.nome,
    d.simbolo,
    AVG(f.preco_usd) AS preco_medio,
    MAX(f.preco_usd) AS preco_max,
    COUNT(*)         AS amostras
FROM {FCT} f
JOIN {DIM} d ON d.moeda_sk = f.moeda_sk   -- fato + dimensão pela chave substituta
GROUP BY d.nome, d.simbolo
ORDER BY preco_medio DESC
LIMIT 10
"""

print(con.execute(consulta).df())