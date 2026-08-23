select
    d.moeda_sk,
    s.coletado_em,
    s.preco_usd,
    s.volume_24h,
    s.market_cap,
    s.variacao_24h,
    s.rank
from {{ ref('stg_mercado') }} s
join {{ ref('dim_moeda') }} d on d.id = s.id