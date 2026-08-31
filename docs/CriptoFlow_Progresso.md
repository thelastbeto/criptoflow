# CriptoFlow — Progresso do Projeto

> Mapa da jornada: o que foi construído, o que se aprendeu e quais ferramentas em cada etapa.
> Serve como visão geral do projeto e roteiro pra explicá-lo em entrevistas.
> Última atualização: 2026-08-12.

---

## Parte I — Fundamentos (ETL básico)

| Etapa | O que se aprendeu a fazer | Ferramentas |
|---|---|---|
| Ambiente | Isolar serviços em containers e o ambiente Python; versionar desde a 1ª linha | Docker, Docker Compose, venv, Git/GitHub |
| Extração | Consumir API REST, tratar JSON, retry com backoff, paginação | Python, `requests` |
| Armazenamento | Modelar tabela relacional (chave composta, normalização, natural vs. substituta) | PostgreSQL, `psycopg2` |
| Transformação + carga | ETL ponta a ponta, UPSERT **idempotente**, `%s` anti-injection | Python, SQL |
| Agendamento | Automatizar com cron (e entender seus limites) | cron |

**Entregável:** um pipeline ETL ponta a ponta (CriptoFlow v0) — portfólio de estágio/júnior.

---

## Parte II — Engenheiro de dados (data lake + orquestração)

| Etapa | O que se aprendeu a fazer | Ferramentas |
|---|---|---|
| Data lake / Bronze | Object storage, Parquet colunar, ELT (guardar o cru), particionamento Hive | MinIO (S3), `boto3`, `pandas`, `pyarrow` |
| Silver | Fan-in, type casting, deduplicação, padronização, overwrite idempotente | `pandas`, `boto3` |
| Gold | Modelagem dimensional em código (star schema, chave substituta, integridade referencial) | `pandas` |
| Servir | Consultar Parquet direto do lake com SQL | DuckDB |
| Transformação (dbt) | SQL versionado e testado (staging + marts), lineage automático, testes de qualidade | dbt (dbt-duckdb) |
| Orquestração | DAG `bronze >> dbt_build`, dependências, rede Docker, permissões de container, pinning de versões | Apache Airflow |
| Transversais | Runbook, conceitos, dicas, fluxo Git (branch + PR + merge) | Git/GitHub, Markdown |

**Parte II concluída ✅** — arquitetura final: **ingestão em Python + transformação em dbt, orquestradas pelo Airflow**. Silver/gold em pandas foram para `legacy/` (substituídas pelos modelos dbt). Complementos opcionais que ficam para depois: ingestão incremental e mais testes de qualidade.

---

## Parte III — Escala e tempo real (pleno/sênior)

| Etapa | O que se aprendeu a fazer | Ferramentas |
|---|---|---|
| Processamento distribuído | Ler/processar o lake em paralelo (partições, lazy evaluation, shuffle); conectar via S3A | Spark (PySpark) |
| Streaming | Producer/consumer, topics/partitions/offsets, ingestão de eventos pro lake em micro-lotes | Apache Kafka (KRaft) |
| Streaming com Spark | "Tabela infinita", event time × processing time, watermark, micro-batches/triggers | Spark Structured Streaming |

**Núcleo da Parte III concluído ✅** — trilha batch (Spark distribuído) + trilha streaming (Kafka → consumidor → lake, e Kafka → Spark Streaming com janela/watermark). Complementos opcionais: lakehouse transacional (Iceberg/Delta), CI/CD de dados, observabilidade/lineage.

**Próximo horizonte (Parte IV — Especialista):** arquitetura de plataforma, governança e contratos de dados, IaC/Kubernetes, LGPD/PII, FinOps, DataOps/SLAs, CDC. Mais decisão e trade-off do que código.

---

## O fio condutor (ciclo de vida da engenharia de dados)

```
Fonte          →  Ingestão          →  Armazenamento    →  Transformação      →  Servir
CoinGecko API      requests / Airflow    MinIO (Parquet)     dbt (staging+marts)   DuckDB
```

Correntes transversais que percorrem tudo: **orquestração** (Airflow), **qualidade** (testes),
**engenharia de software** (Git, PRs, runbook) e **reprodutibilidade** (Docker, pinning de versões).

---

## Documentos de apoio do projeto

- **Runbook de Erros** — problemas enfrentados + como debugar (formato: sintoma → solução rápida → árvore de decisão → causa → verificação → lições).
- **Livro de Conceitos** — notas de conceito (Parte A) + dicionário de expressões no formato *o que é* / *o que avalia* (Parte B).
- **Dicas & Truques** — atalhos práticos de bolso (Terminal, WSL, Python, SQL, Git, Docker, Airflow, dbt, debug).
- **Progresso** — este documento.

---

## Princípio-guia

Em cada etapa, o foco não foi decorar a ferramenta, mas entender **o problema que ela resolve** — porque
as ferramentas mudam, mas as categorias (armazenamento, transformação, orquestração, modelagem,
confiabilidade) permanecem.
