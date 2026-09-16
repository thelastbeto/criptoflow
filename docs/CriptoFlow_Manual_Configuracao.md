# CriptoFlow — Manual de Configuração

> Roteiro **do zero ao tudo rodando**, reduzido ao necessário. Ambiente de referência: **Windows + WSL2 (Ubuntu)**.
> Este manual cobre o que **não** está no repositório (pré-requisitos, arquivos de segredo, sequência de
> comandos). Os scripts, o `docker-compose.yml`, os DAGs e o projeto dbt já estão versionados.
> Para o *porquê* de cada escolha, ver o **Livro de Conceitos**; para erros comuns, o **Runbook**.

---

## 1. Pré-requisitos

- **Docker Desktop** com a **integração WSL** ligada (Settings → Resources → WSL Integration).
- **Python 3.x** + `venv` (`sudo apt install -y python3 python3-venv python3-pip`).
- **Java** (o Spark roda na JVM): `sudo apt install -y openjdk-17-jdk-headless`.
- **Git**.
- Trabalhar na home do Linux (`~/projetos/criptoflow`), **nunca** em `/mnt/c/...`.

## 2. Clonar o projeto

```bash
git clone https://github.com/thelastbeto/criptoflow.git
cd criptoflow
```

## 3. Criar os segredos (`.env`) — NÃO está no repo

Copie o exemplo e preencha com os valores reais:

```bash
cp .env.example .env
```

Conteúdo do `.env` (o `.env` é ignorado pelo Git; nunca committar) — preencha com **seus** valores:
```
MINIO_KEY=<usuario-do-minio>
MINIO_SECRET=<senha-do-minio>
POSTGRES_USER=<usuario-do-postgres>
POSTGRES_PASSWORD=<senha-do-postgres>
POSTGRES_DB=<nome-do-banco>
```

## 4. Subir a infraestrutura (Docker)

```bash
docker compose up -d
docker compose ps          # todos os serviços "running"
docker compose config      # valida o YAML, se precisar
```

**Portas publicadas (host → container):**

| Serviço | Host | Container | Acesso |
|---|---|---|---|
| PostgreSQL | 5433 | 5432 | `localhost:5433` |
| MinIO — API S3 | 9100 | 9000 | código/DuckDB/Spark |
| MinIO — Console | 9101 | 9001 | navegador: `localhost:9101` |
| Airflow | 8080 | 8080 | navegador: `localhost:8080` |
| Kafka | 9092 | 9092 | `localhost:9092` |

**Configs sensíveis a saber (já no compose):**
- MinIO/Postgres leem os segredos via `${VAR}` (do `.env`).
- Airflow: `user: "1000:0"` (permissão nos arquivos montados), monta `~/.dbt` (profile do dbt) e recebe
  `MINIO_ENDPOINT=http://minio:9000` + `MINIO_KEY`/`MINIO_SECRET` via `${VAR}`.
- Kafka (KRaft): broker em `0.0.0.0:9092`, **controller e advertised em `localhost`** (senão o container morre).

## 5. Ambiente Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 6. Configurar o dbt (`~/.dbt/profiles.yml`) — NÃO está no repo

```bash
mkdir -p ~/.dbt
```
Crie `~/.dbt/profiles.yml`:
```yaml
criptoflow_dbt:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: 'criptoflow.duckdb'
      extensions:
        - httpfs
      settings:
        s3_endpoint: "{{ env_var('DBT_S3_ENDPOINT', 'localhost:9100') }}"
        s3_access_key_id: '<usuario-do-minio>'
        s3_secret_access_key: '<senha-do-minio>'
        s3_use_ssl: false
        s3_url_style: 'path'
        s3_region: 'us-east-1'
```
Testar: `cd criptoflow_dbt && dbt debug` → deve dar `All checks passed!`

## 7. Rodar

**Batch (manual):**
```bash
python3 bronze.py                       # ingestão CoinGecko → MinIO (bronze)
cd criptoflow_dbt && dbt build          # transformação: staging + marts + testes
```

**Batch (orquestrado pelo Airflow):**
1. Senha do admin: `docker compose exec airflow cat /opt/airflow/standalone_admin_password.txt`
2. Acessar `localhost:8080` (usuário `admin`, **aba anônima** pra evitar CSRF).
3. Ativar e disparar o DAG `criptoflow_medallion` (`bronze >> dbt_build`).

**Servir (consulta analítica):**
```bash
python3 consultar.py                    # DuckDB sobre a gold no lake
```

**Streaming (dois/três terminais):**
```bash
python3 produtor.py                     # publica preços no Kafka
python3 consumidor.py                   # Kafka → bronze (lake)
python3 spark_streaming.py              # Spark: janela + watermark ao vivo
```

**Lakehouse (Delta):**
```bash
python3 lakehouse.py                    # tabela Delta com ACID + time travel
```

## 8. GitHub / CI (setup do repositório)

- `.github/workflows/ci.yml` → valida `py_compile` + `dbt parse` a cada PR.
- `.github/dbt/profiles.yml` → profile de CI (DuckDB local, sem S3).
- **Branch protection** (Settings → Branches, regra na `main`): marcar *Require status checks to pass*
  (check `validar`); em projeto **solo**, **não** marcar *Require approvals* (não dá pra aprovar o próprio PR).

## 9. Versões pinadas (reprodutibilidade)

| Item | Versão |
|---|---|
| pyarrow | `25.0.0` |
| dbt-duckdb | `1.11.x` (confirmar com `pip show dbt-duckdb`) |
| PySpark | `4.2.0` |
| hadoop-aws (S3A) | **igual ao Hadoop do Spark** (`3.5.0`) — confira em `.../pyspark/jars` |
| spark-sql-kafka | `org.apache.spark:spark-sql-kafka-0-10_2.13:4.2.0` |
| Imagem Airflow | `apache/airflow:2.10.5` |
| Imagem Kafka | `apache/kafka:3.9.0` (confirmar tag estável) |

> Os jars do Spark (S3A, kafka) são baixados na 1ª execução via `spark.jars.packages` (precisa de internet).

## 10. Gotchas frequentes (detalhes no Runbook)

- **`localhost` × container:** no host use `localhost:<porta publicada>`; dentro de container, `<serviço>:<porta interna>`.
- **Airflow demora a subir** após `--force-recreate` (reinstala libs) — espere `Airflow is ready` no log.
- **Conflito de porta** → escolha outra (padrão que se repete).
- **Nunca committar o `.env`** — confirme com `git status`.
