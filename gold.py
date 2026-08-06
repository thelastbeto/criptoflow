import io
import boto3
import pandas as pd
from dotenv import load_dotenv
import os

load_dotenv()

MINIO_ENDPOINT = "http://localhost:9100"
MINIO_KEY      = os.getenv('MINIO_KEY')
MINIO_SECRET   = os.getenv('MINIO_SECRET')
BUCKET         = "criptoflow"

def cliente_s3():
    return boto3.client("s3", endpoint_url=MINIO_ENDPOINT,
                        aws_access_key_id=MINIO_KEY, aws_secret_access_key=MINIO_SECRET)

def ler_silver(s3):
    resp = s3.list_objects_v2(Bucket=BUCKET, Prefix="silver/mercado/")
    dfs = []
    for o in resp.get("Contents", []):
        if o["Key"].endswith(".parquet"):
            corpo = s3.get_object(Bucket=BUCKET, Key=o["Key"])["Body"].read()
            dfs.append(pd.read_parquet(io.BytesIO(corpo)))
    if not dfs:
        raise RuntimeError("Nenhum arquivo na silver.")
    return pd.concat(dfs, ignore_index=True)

def gravar_parquet(s3, df, chave):
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    s3.put_object(Bucket=BUCKET, Key=chave, Body=buf.getvalue())
    print(f"gold: s3://{BUCKET}/{chave} ({len(df)} linhas)")

def construir_dim_moeda(silver):
    """Dimensão: identidade da moeda + chave substituta inteira."""
    dim = (silver[["id", "nome", "simbolo"]]
           .drop_duplicates(subset=["id"])
           .sort_values("id")
           .reset_index(drop=True))
    dim.insert(0, "moeda_sk", range(1, len(dim) + 1))   # <- chave substituta (surrogate)
    return dim

def construir_fct_precos(silver, dim):
    """Fato: uma linha por moeda por snapshot, com FK pra dimensão."""
    fct = silver.merge(dim[["moeda_sk", "id"]], on="id", how="left")
    return fct[["moeda_sk", "coletado_em", "preco_usd",
                "volume_24h", "market_cap", "variacao_24h", "rank"]]

if __name__ == "__main__":
    s3 = cliente_s3()
    silver = ler_silver(s3)
    dim = construir_dim_moeda(silver)
    fct = construir_fct_precos(silver, dim)
    gravar_parquet(s3, dim, "gold/dim_moeda/dim_moeda.parquet")
    gravar_parquet(s3, fct, "gold/fct_precos/fct_precos.parquet")
    print("Camada gold (star schema) atualizada.")