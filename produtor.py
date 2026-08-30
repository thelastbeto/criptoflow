import json, time, requests
from kafka import KafkaProducer

BASE = "https://api.coingecko.com/api/v3"

producer = KafkaProducer(
    bootstrap_servers="localhost:9092",
    key_serializer=lambda k: k.encode(),
    value_serializer=lambda v: json.dumps(v).encode(),
)

print("Produtor iniciado. Ctrl+C para parar.")
try:
    while True:
        try:
            r = requests.get(
                f"{BASE}/simple/price",
                params={"ids": "bitcoin,ethereum,solana", "vs_currencies": "usd"},
                timeout=30,
            )
            if r.status_code == 429:                       # rate limit
                print("429 (rate limit) — esperando 60s")
                time.sleep(60)                             # backoff maior no 429
                continue
            r.raise_for_status()
            agora = time.time()
            for moeda, val in r.json().items():
                evento = {"id": moeda, "preco_usd": val["usd"], "ts": agora}
                producer.send("precos-cripto", key=moeda, value=evento)
                print("publicado:", evento)
            producer.flush()
        except requests.RequestException as e:             # rede/API instável
            print(f"erro transitório: {e} — continuando")
        time.sleep(20)                                     # espaçamento normal
except KeyboardInterrupt:
    print("Parando produtor.")
finally:
    producer.close()