select
    id,
    symbol                              as simbolo,
    name                                as nome,
    cast(current_price as double)       as preco_usd,
    cast(total_volume as double)        as volume_24h,
    cast(market_cap as double)          as market_cap,
    cast(market_cap_rank as integer)    as rank,
    cast(price_change_percentage_24h as double) as variacao_24h,
    cast(coletado_em as timestamp)      as coletado_em
from read_parquet('s3://criptoflow/bronze/mercado/**/*.parquet')