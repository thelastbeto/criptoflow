import os
import duckdb
from credentials import Credentials

# --- Config do MinIO (porta 9100 = API S3, a que remapeamos) ---

MINIO_ENDPOINT = Credentials.endpoints()['minio']
MINIO_KEY      = Credentials.minio()['key']
MINIO_SECRET   = Credentials.minio()['secret']


con = duckdb.connect()

con.execute('INSTALL httpfs; LOAD httpfs;')
con.execute(f"SET s3_endpoint={MINIO_ENDPOINT};")
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