import io, json
from datetime import datetime, timezone
import boto3
import pandas as pd
from extrair import extrair_mercado
from dotenv import load_dotenv
import os

# --- Config do MinIO (porta 9100 = API S3, a que remapeamos) ---
load_dotenv()

MINIO_ENDPOINT = "http://localhost:9100"
MINIO_KEY      = os.getenv('MINIO_KEY')
MINIO_SECRET   = os.getenv('MINIO_SECRET')
BUCKET         = "criptoflow"

def cliente_s3():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_KEY,
        aws_secret_access_key=MINIO_SECRET,
    )

def garantir_bucket(s3):
    existentes = [b["Name"] for b in s3.list_buckets()["Buckets"]]
    if BUCKET not in existentes:
        s3.create_bucket(Bucket=BUCKET)
        print(f"Bucket '{BUCKET}' criado.")

def gravar_bronze(bruto, coletado_em):
    df = pd.DataFrame(bruto)              # o JSON cru vira DataFrame (TODAS as colunas)
    df["coletado_em"] = coletado_em      # metadado da coleta

    # Parquet é colunar e não gosta de células aninhadas (dict/list).
    # Serializamos essas colunas como texto JSON para caberem no formato.
    for col in df.columns:
        if df[col].apply(lambda v: isinstance(v, (dict, list))).any():
            df[col] = df[col].apply(lambda v: json.dumps(v) if isinstance(v, (dict, list)) else v)

    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False)   # DataFrame -> Parquet, em memória
    buffer.seek(0)

    dia = coletado_em.strftime("%Y-%m-%d")
    ts  = coletado_em.strftime("%Y%m%dT%H%M%S")
    chave = f"bronze/mercado/dia={dia}/mercado_{ts}.parquet"

    s3 = cliente_s3()
    garantir_bucket(s3)
    s3.put_object(Bucket=BUCKET, Key=chave, Body=buffer.getvalue())
    print(f"Gravado s3://{BUCKET}/{chave} ({len(df)} linhas, {len(df.columns)} colunas)")

if __name__ == "__main__":
    agora = datetime.now(timezone.utc)
    bruto = extrair_mercado(total=250)
    gravar_bronze(bruto, agora)