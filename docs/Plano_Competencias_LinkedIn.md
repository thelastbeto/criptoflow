# Plano de Competências — Roberto Junior

> **Para o time de marketing.** Este documento complementa o plano de reposicionamento do LinkedIn:
> ele fornece a **substância** (as competências reais, com nível de confiança) para preencher headline,
> "Sobre", "Competências" e "Em destaque".
>
> **Princípio (o mesmo do plano):** listar só o que é **defensável numa call técnica de 20 minutos**.
> A força do posicionamento é a **trajetória em movimento + fundamentos sólidos**, não inflar cargo.
>
> **Base factual:** experiência de 4 anos como Analista de Sistemas + o projeto **CriptoFlow** (plataforma
> de dados ponta a ponta construída do zero: batch e streaming), que serve de prova concreta das skills abaixo.

---

## 1. Competências por nível de confiança

Tierado com honestidade — isso é o que decide o que vai no headline vs. o que se menciona como "em evolução".

### 🟢 Tier 1 — Domino e defendo com profundidade
*(pode ir no headline, no topo das skills, e sustentar em entrevista)*
- **SQL** (Oracle, SQL Server; analítico: JOINs, agregações, window functions, deduplicação, `NULLS LAST`)
- **Python** (consumo de API REST, tratamento de erros/resiliência, pandas)
- **Modelagem de dados** (normalização, star schema, chave natural × substituta, granularidade)
- **ELT e arquitetura em camadas (Medallion: bronze/silver/gold)**
- **Idempotência e confiabilidade de pipelines** (UPSERT, reprocessamento sem duplicar)
- **Docker / Docker Compose** (ambientes reproduzíveis, rede entre serviços, volumes)
- **Git / GitHub** (fluxo profissional: branch → PR → merge)

### 🟡 Tier 2 — Uso na prática e sei discutir
*(pode listar como skill; menciona como "trabalho com", não como "especialista")*
- **Apache Airflow** (DAGs, dependências, orquestração — construiu um DAG `bronze >> dbt`)
- **dbt** (staging/marts, testes de qualidade, lineage, materialização view/table)
- **Data lake / object storage** (MinIO compatível com S3, Parquet, particionamento por data)
- **DuckDB** (consulta analítica sobre Parquet no lake)
- **Apache Spark / PySpark** (processamento distribuído: partições, lazy evaluation, shuffle; leitura via S3A)
- **Apache Kafka** (streaming: producer/consumer, topics, partitions, offsets, consumer groups)
- **Spark Structured Streaming** (event time × processing time, watermark, micro-batches)

### 🔵 Tier 3 — Conhecimento inicial / em construção
*(mencionar com honestidade; NÃO vender como expertise)*
- **Cloud / BigQuery** — certificação concluída; prática hands-on em produção ainda em construção.
- **Governança de dados** — certificação; nível conceitual.
- **Ainda não domina (não listar como skill por enquanto):** Kubernetes, IaC/Terraform, lakehouse
  transacional (Iceberg/Delta), CI/CD de dados. → estão no **roadmap** do projeto.

---

## 2. Skills nomeadas para o LinkedIn (o que adicionar/ordenar)

**Top 3 fixadas (as que pesam na busca):** `Python` · `SQL` · `Engenharia de Dados`

**Adicionar como skills nomeadas:**
`ETL/ELT` · `Modelagem de Dados` · `dbt` · `Apache Airflow` · `Apache Spark (PySpark)` · `Apache Kafka` ·
`Docker` · `Data Lake` · `Parquet` · `DuckDB` · `Streaming de Dados`

**Não adicionar ainda** (o plano já alerta): `Kubernetes` (estava com erro "Kubernets" e não é defensável hoje).

---

## 3. Termos agora defensáveis no headline

O plano sugeriu, com razão, a Opção A ("Engenheiro de Dados em formação · Analista de Sistemas há 4 anos").
Graças ao CriptoFlow, agora dá pra **fortalecer honestamente** os termos de pipeline:

> **Engenheiro de Dados em formação · Analista de Sistemas há 4 anos**
> **| SQL, Python e Pipelines de Dados (Airflow · dbt · Spark · Kafka)**

Continua honesto (*em formação*), mas os termos técnicos agora têm **um projeto real por trás**, não são
palavras soltas. (Usar `Spark`/`Kafka` no headline só porque ele está confortável defendendo o básico deles — e está.)

---

## 4. A prova — projeto CriptoFlow (para a seção "Em destaque")

O que sustenta todas as skills acima. Sugestão de card:

> **CriptoFlow — Plataforma de Dados de Criptomoedas**
> Pipeline ponta a ponta (batch + streaming) construído do zero: ingestão da API CoinGecko, data lake em
> camadas (MinIO/Parquet), transformação com dbt, orquestração com Airflow, e streaming com Kafka + Spark.
> *Repositório com README, diagrama de arquitetura e documentação (runbook, conceitos).*

Isso transforma "eu estudei" em "eu construí e sei explicar" — a diferença que fecha uma entrevista.

---

## 5. Ideias de conteúdo (matéria-prima para os posts)

Todas nascem do que ele **realmente fez** — conteúdo autêntico, do jeito que o plano recomenda ("ensine
uma coisa pequena e concreta"):

1. "Por que ELT e não ETL? A decisão que definiu a última década de dados."
2. "Idempotência: por que rodar o pipeline duas vezes não pode duplicar dados."
3. "pandas × Spark: a métrica que decide qual usar é a RAM (e o meio-termo que quase ninguém lembra: DuckDB)."
4. "O que é um data lake em camadas (bronze/silver/gold), explicado com um projeto real."
5. "listeners × advertised no Kafka: um bug de config e o que ele me ensinou." (história de debug real)
6. "Meu runbook de erros: como transformo cada bug num aprendizado documentado."
7. "A mentalidade que mais me fez crescer em dados: prova, não chuta."

Cada um vira 1 post; cadência de **1–2/semana** (como o plano sugere).

---

## 6. Guardrails de honestidade (o que NÃO afirmar)

- **Não se vender como sênior.** O ativo é "analista sólido migrando para dados, com fundamentos reais".
- **Cloud como "em construção"** até levar o CriptoFlow para AWS/GCP (está no roadmap).
- **Nada de Kubernetes/IaC** como skill até ter prática — listar o que não se defende é o maior risco.
- Regra de ouro: **se travar numa call de 20 min, sai do perfil.**

---

*Documento de competências gerado como apoio ao reposicionamento. Os níveis refletem o que foi
efetivamente construído e compreendido no projeto CriptoFlow + a experiência prévia — ajuste conforme evoluir.*
