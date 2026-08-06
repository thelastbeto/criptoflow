import io
import boto3
import pandas as pd
from extrair import extrair_mercado
from dotenv import load_dotenv
import os

load_dotenv()

MINIO_ENDPOINT = "http://localhost:9100"
MINIO_KEY      = os.getenv('MINIO_KEY')
MINIO_SECRET   = os.getenv('MINIO_SECRET')
BUCKET         = "criptoflow"

# Mapa: coluna da bronze (fonte) -> coluna padronizada da silver
COLUNAS = {
    "id": "id", "symbol": "simbolo", "name": "nome",
    "current_price": "preco_usd", "total_volume": "volume_24h",
    "market_cap": "market_cap", "market_cap_rank": "rank",
    "price_change_percentage_24h": "variacao_24h", "coletado_em": "coletado_em",
}

def cliente_s3():
    return boto3.client("s3", 
                        endpoint_url=MINIO_ENDPOINT,
                        aws_access_key_id=MINIO_KEY, 
                        aws_secret_access_key=MINIO_SECRET)

def ler_bronze(s3):
    """Fan-in: lê TODOS os Parquet da bronze e junta num só DataFrame."""
    resp = s3.list_objects_v2(Bucket=BUCKET, Prefix="bronze/mercado/")
    dfs = []
    for obj in resp.get("Contents", []):
        if obj["Key"].endswith(".parquet"):
            corpo = s3.get_object(Bucket=BUCKET, Key=obj["Key"])["Body"].read()
            dfs.append(pd.read_parquet(io.BytesIO(corpo)))
    if not dfs:
        raise RuntimeError("Nenhum arquivo encontrado na bronze.")
    return pd.concat(dfs, ignore_index=True)

def transformar_silver(df):
    # 1. seleciona e renomeia (padroniza o schema)
    df = df[list(COLUNAS.keys())].rename(columns=COLUNAS)
    # 2. tipa: números viram números; texto ruim vira NaN em vez de quebrar
    for c in ["preco_usd", "volume_24h", "market_cap", "rank", "variacao_24h"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["coletado_em"] = pd.to_datetime(df["coletado_em"], utc=True)
    # 3. deduplica: uma linha por (id, coletado_em), mantendo a mais recente
    df = df.sort_values("coletado_em").drop_duplicates(subset=["id", "coletado_em"], keep="last")
    return df

def gravar_silver(df):
    s3 = cliente_s3()
    df = df.copy()
    df["dia"] = df["coletado_em"].dt.strftime("%Y-%m-%d")
    for dia, grupo in df.groupby("dia"):
        grupo = grupo.drop(columns=["dia"])
        buffer = io.BytesIO()
        grupo.to_parquet(buffer, index=False)
        chave = f"silver/mercado/dia={dia}/mercado.parquet"   # nome fixo -> overwrite idempotente
        s3.put_object(Bucket=BUCKET, Key=chave, Body=buffer.getvalue())
        print(f"silver: s3://{BUCKET}/{chave} ({len(grupo)} linhas)")

if __name__ == "__main__":
    s3 = cliente_s3()
    bruto  = ler_bronze(s3)
    limpo  = transformar_silver(bruto)
    gravar_silver(limpo)
    print("Camada silver atualizada.")