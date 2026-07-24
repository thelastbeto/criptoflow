import requests

import requests, time

BASE = "https://api.coingecko.com/api/v3"

def extrair_mercado(vs="usd", n=50, tentativas=3):
    """Extrai o snapshot de mercado das top N moedas."""

    params = {"vs_currency": vs, "order": "market_cap_desc",
              "per_page": n, "page": 1}
    
    for t in range(tentativas):
        r = requests.get(f"{BASE}/coins/markets", params=params, timeout=30)
        if r.status_code == 429:      # rate limit atingido
            time.sleep(2 ** t)        # espera 1s, 2s, 4s... (backoff exponencial)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("Falha ao extrair após várias tentativas")

if __name__ == "__main__":
    dados = extrair_mercado(n=50)
    print(f"Coletadas {len(dados)} moedas.")
    for moeda in dados:
        print(moeda["id"], moeda["current_price"], moeda["total_volume"])