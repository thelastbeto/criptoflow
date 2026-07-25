import requests

import requests, time

BASE = "https://api.coingecko.com/api/v3"

def extrair_mercado(vs="usd", total=250, por_pagina=250, tentativas=3):
    """Extrai o snapshot de mercado das top N moedas, paginando."""
    todas, pagina = [], 1
    while len(todas) < total:
        params = {"vs_currency": vs, "order": "market_cap_desc",
                  "per_page": por_pagina, "page": pagina}

        for t in range(tentativas):
            r = requests.get(f"{BASE}/coins/markets", params=params, timeout=30)
            if r.status_code == 429:                 # rate limit
                time.sleep(2 ** t)                   # backoff exponencial
                continue
            r.raise_for_status()
            lote = r.json()
            break
        else:
            # só chega aqui se o for terminou SEM break → todas as tentativas foram 429
            raise RuntimeError(
                f"Rate limit persistente na página {pagina} após {tentativas} tentativas"
            )

        if not lote:
            print("Não existem mais dados para coletar. Parando.")
            break
        todas.extend(lote)
        pagina += 1
    return todas[:total]

if __name__ == "__main__":
    dados = extrair_mercado(n=50)
    print(f"Coletadas {len(dados)} moedas.")
    for moeda in dados:
        print(moeda["id"], moeda["current_price"], moeda["total_volume"])