import psycopg2
from datetime import datetime, timezone
from extrair import extrair_mercado

def transformar(bruto):
    """Seleciona e limpa apenas os campos que interessam."""
    agora = datetime.now(timezone.utc)
    return [(
        m["id"], m["symbol"], m["name"],
        m["current_price"], m["total_volume"],
        m["market_cap"], m.get("price_change_percentage_24h"), agora,
    ) for m in bruto]

def carregar(linhas):
    """Grava no Postgres com UPSERT (idempotente na mesma coleta)."""
    conn = psycopg2.connect(
        host="localhost", port=5433, dbname="criptoflow",
        user="criptoflow", password="criptoflow",
    )
    with conn, conn.cursor() as cur:
        cur.executemany("""
            INSERT INTO mercado_bruto
            (id, simbolo, nome, preco_usd, volume_24h,
             market_cap, variacao_24h, coletado_em)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id, coletado_em) DO NOTHING
        """, linhas)
    conn.close()

def carregar_moedas(bruto):
    linhas = [(m['id'], m['symbol'], m['name']) for m in bruto]

    conn = psycopg2.connect(
        host="localhost", port=5433, dbname="criptoflow",
        user="criptoflow", password="criptoflow",
    )

    with conn, conn.cursor() as cur:
            cur.executemany("""
                INSERT INTO moedas
                (id, simbolo, nome)
                VALUES (%s,%s,%s)
                ON CONFLICT (id) DO NOTHING
            """, linhas)
    conn.close()

if __name__ == "__main__":
    bruto = extrair_mercado(por_pagina=250)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    carregar(transformar(bruto))
    print("CriptoFlow v0: ingestão concluída as {}.".format(now))
    carregar_moedas(bruto)
    print("CriptoFlow v0: ingestão de novas moedas concluída as {}.".format(now))