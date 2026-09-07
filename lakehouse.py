import pandas as pd
from deltalake import write_deltalake, DeltaTable
from credentials import Credentials

storage_options = {
    "AWS_ENDPOINT_URL": Credentials.endpoints()['minio'],
    "AWS_ACCESS_KEY_ID": Credentials.minio()['key'],
    "AWS_SECRET_ACCESS_KEY": Credentials.minio()['secret'],
    "AWS_ALLOW_HTTP": "true",
    "AWS_S3_ALLOW_UNSAFE_RENAME": "true",   # S3/MinIO não tem rename atômico; ok pra 1 escritor
    "AWS_REGION": "us-east-1",
}
TABELA = "s3://criptoflow/lakehouse/precos_delta"

# --- Escrita 1 → cria a versão 0 ---
df1 = pd.DataFrame({"id": ["bitcoin", "ethereum"], "preco_usd": [78000.0, 2500.0]})
write_deltalake(TABELA, df1, mode="overwrite", storage_options=storage_options)
print("Versão 0 gravada.")

# --- Escrita 2 (append) → cria a versão 1 ---
df2 = pd.DataFrame({"id": ["bitcoin", "ethereum"], "preco_usd": [79000.0, 2520.0]})
write_deltalake(TABELA, df2, mode="append", storage_options=storage_options)
print("Versão 1 gravada.")

# --- TIME TRAVEL ---
dt = DeltaTable(TABELA, storage_options=storage_options)
print("\nHistórico de versões:")
for h in dt.history():
    print(" -", h.get("version"), h.get("operation"), h.get("timestamp"))

print("\nEstado ATUAL (todas as escritas):")
print(DeltaTable(TABELA, storage_options=storage_options).to_pandas())

print("\nComo era na VERSÃO 0 (só a primeira escrita):")
print(DeltaTable(TABELA, version=0, storage_options=storage_options).to_pandas())