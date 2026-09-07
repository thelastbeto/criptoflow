import json, io
from datetime import datetime, timezone
import boto3
import pandas as pd
from kafka import KafkaConsumer
from credentials import Credentials

BUCKET = 'criptoflow'

s3 = boto3.client("s3", 
                  endpoint_url=Credentials.endpoints()['minio'],
                  aws_access_key_id=Credentials.minio()['key'], 
                  aws_secret_access_key=Credentials.minio()['secret'],
                  )


consumer = KafkaConsumer(
    "precos-cripto",
    bootstrap_servers="localhost:9092",
    group_id="gravador-bronze",              # o consumer group
    auto_offset_reset="earliest",            # sem offset salvo? leia do começo
    value_deserializer=lambda b: json.loads(b),
)

print("Consumidor iniciado. Lendo 'precos-cripto'. Ctrl+C para parar.")
buffer = []

try:
    for msg in consumer:
        buffer.append(msg.value)
        print("consumido:", msg.value)
        if len(buffer) >= 10:                # grava em MICRO-LOTES de 10
            df = pd.DataFrame(buffer)
            agora = datetime.now(timezone.utc)
            chave = f"bronze/precos_stream/dia={agora:%Y-%m-%d}/precos_{agora:%Y%m%dT%H%M%S}.parquet"
            buf = io.BytesIO(); df.to_parquet(buf, index=False); buf.seek(0)
            s3.put_object(Bucket=BUCKET, Key=chave, Body=buf.getvalue())
            print(f"gravado {len(buffer)} eventos -> s3://{BUCKET}/{chave}")
            buffer = []
except KeyboardInterrupt:
    print("Parando consumidor.")
finally:
    consumer.close()