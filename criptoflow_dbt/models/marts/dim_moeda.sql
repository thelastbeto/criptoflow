with base as (
    select
        id, 
        nome, 
        simbolo,
        row_number() over (partition by id order by id) as rn
    from {{ ref('stg_mercado') }}
)
select
    row_number() over (order by id) as moeda_sk,   -- chave substituta
    id, 
    nome, 
    simbolo
from base
where rn = 1                                        -- uma linha por moeda