# CriptoFlow — Dicas & Truques (Coding Cheats)

> Atalhos práticos de bolso coletados na construção do projeto. Aqui NÃO é definição (isso é o
> Livro de Conceitos) nem erro (isso é o Runbook) — são comandos e macetes do dia a dia.
> Última atualização: 2026-08-23.

---

## Terminal / Linux
- `ls -a` → mostra arquivos **ocultos** (dotfiles começam com `.`, ex.: `.env`, `.dbt`).
- `code <caminho>` → abre **qualquer** arquivo no VS Code, mesmo oculto ou fora do projeto:
  `code ~/.dbt/profiles.yml`; `code .` abre a pasta atual.
- `find <dir> -type f` → lista todos os arquivos, recursivamente.
- `grep -iE "a|b|c"` → busca vários termos (`-i` ignora maiúsc/minúsc, `-E` habilita o `|` = "ou").
  `grep -A N` mostra N linhas **depois** de cada acerto. *Cuidado:* grep é literal e pega a palavra
  dentro de outra (ex.: "ImportError"). Leia o acerto ou refine o termo.
- `nano arquivo` → salvar `Ctrl+O`, sair `Ctrl+X`. Sair do vim: `Esc` → `:wq` (salva) / `:q!` (descarta).
- `curl -I <url>` → testa conectividade e mostra os headers HTTP (ótimo para health check).
- `id -u` → mostra o seu uid (normalmente 1000).
- `python3 -c "import X; print(X.__version__)"` → versão de uma lib.
- `pip show <pacote> | grep Version` → versão instalada de um pacote.

## WSL (Windows + Ubuntu)
- Trabalhe na home do Linux (`~`), **nunca** em `/mnt/c/...` — muito mais rápido e sem dor de permissão.
- Ferramentas Linux **não abrem navegador** no WSL (`xdg-open` falha) — abra a URL manualmente no
  navegador do Windows.
- O cron **não sobe sozinho**: `sudo service cron start`.
- Portas reservadas do Windows podem bloquear o publish do Docker silenciosamente. Ver as faixas
  (no PowerShell): `netsh int ipv4 show excludedportrange protocol=tcp`. Solução: use outra porta.

## Python
- `dict.get("chave", padrao)` → campos opcionais sem quebrar se faltar.
- `os.getenv("VAR", "padrao")` → config por ambiente (12-factor).
- `for ... else:` → o `else` roda só se o `for` terminar **sem** `break` (ideal p/ "esgotou tentativas").
- `if __name__ == "__main__":` → separa "o que rodar" de "importável"; envolva a lógica numa função
  `executar()`/`main()`.
- Placeholders `%s` no SQL (nunca concatene string) → segurança (anti-injection) + correção.
- `io.BytesIO()` (binário) / `io.StringIO()` (texto) → "arquivo em memória" pra não tocar o disco.
- Capture exceção **específica** (`except requests.RequestException as e:`), nunca `except:` pelado;
  encadeie com `raise ... from e` pra preservar a causa.
- Venv: `source .venv/bin/activate` (prompt mostra `(.venv)`); `deactivate` pra sair.
- **Fixe versões** (`requirements.txt`, `pyarrow==X`) — reprodutibilidade.

## SQL / DuckDB
- `ORDER BY <alias>` → dá pra ordenar pelo alias do `SELECT` (DRY).
- `ORDER BY col DESC NULLS LAST` → evita NULL aparecendo no topo do ranking.
- "Última linha por chave": `row_number() over (partition by chave order by data desc)` e filtrar `= 1`
  (no DuckDB dá pra usar `QUALIFY`).
- "Último snapshot": `WHERE ts = (SELECT max(ts) FROM tabela)`.
- DuckDB lê Parquet do S3/MinIO: `INSTALL httpfs; LOAD httpfs;` + `SET s3_endpoint='host:porta'` (sem `http://`).

## Git / GitHub
- `git branch -a` → todas as branches (locais e remotas).
- `git branch -M main` → renomeia a branch atual.
- `git log A..B --oneline` → commits em B que não estão em A (use prefixo `origin/` para remotas).
- `git fetch --prune` → remove referências de branches remotas já deletadas.
- `git remote set-url origin <url>` → troca a URL do remote.
- `git status` antes de commitar → confira que segredos/artefatos não vão junto.
- Fluxo: branch → commit → push → PR → merge → limpeza. **Pushed ≠ merged** (o merge é o clique no PR).

## Docker / Compose
- `docker compose config` → config resolvida (estado **desejado**); valida o YAML.
- `docker compose ps` → coluna PORTS: `0.0.0.0:host->container` = **publicada**; `container/tcp` = só **exposta**.
- `docker compose ps -a` → mostra também os containers **parados/mortos** (o `ps` normal esconde). Container
  que **sobe e morre**? O motivo está no `docker compose logs <svc>` (não no output do `up`); o exit code aparece no `ps -a`.
- `docker port <container>` / `docker inspect` → estado **real** do container.
- `docker compose logs <svc> --tail N` (`-f` segue ao vivo; `Ctrl+C` para de seguir, não para o container).
- `docker compose exec <svc> <cmd>` → roda comando **dentro** do container.
- `docker compose up -d --force-recreate <svc>` → aplica config nova.
- `docker compose rm -sf <svc>` → para e remove o container **sem** apagar volumes.
- Rede: containers do mesmo compose se falam por **nome do serviço + porta interna** (`minio:9000`);
  `localhost` dentro do container = ele mesmo; para o host = `host.docker.internal`.
- Portas `host:container` → esquerda = você (host), direita = porta interna.
- Volume **nomeado** (declara em `volumes:`) × **bind mount** (`./x`, não declara).
- `Permission denied` em volume montado → uid do container ≠ dono do arquivo no host.
  Fix padrão: `user: "$(id -u):0"` no serviço.

## Airflow
- Pegar a senha do admin (modo standalone):
  `docker compose exec airflow cat /opt/airflow/standalone_admin_password.txt`. O usuário é sempre `admin`.
- A senha **muda a cada `--force-recreate`** (o metadado do standalone é efêmero) — pegue de novo depois de recriar.
- Depois de recriar, use **aba anônima** pra evitar "CSRF session token missing" (cookie de sessão velho).
- Ver o erro de uma task: UI → Graph/Grid → clica na task → **Logs** (não a aba "Event Log", que só mostra estados).
- DAG com código quebrado aparece como banner vermelho **"Broken DAG"** na UI — isso **não** derruba o webserver.

## dbt
- `dbt debug` → testa projeto + conexão (diagnóstico nº 1).
- `dbt ls` → lista os recursos reconhecidos (**o nome do modelo = o nome do arquivo!**).
- `dbt run --select <modelo>` → roda um modelo específico.
- `dbt show --select <modelo> --limit 5` → espia o resultado.
- `dbt test` → roda os testes do `schema.yml`.
- `dbt docs generate && dbt docs serve --port 8081` → gera e serve o lineage (use `--port` p/ evitar conflito).
- `--project-dir <caminho>` → roda apontando pra outro diretório (usado pelo Airflow).
- Config vem da **pasta**: `models/staging/` recebe a config de `staging:`.
- `env_var('VAR', 'padrao')` no `profiles.yml` (Jinja) → config por ambiente.
- Segredos (`profiles.yml`) em `~/.dbt`, fora do repo; ignore `*.duckdb`, `target/`, `logs/`.

## Spark (PySpark)
- Spark precisa de **Java** (roda na JVM): `sudo apt install -y openjdk-17-jdk-headless`.
- `master="local[*]"` → roda local usando **todos os cores** como "cluster" (em produção, aponta pro cluster real).
- Descobrir a versão do Hadoop embutida (pra casar o S3A):
  `ls $(python3 -c "import pyspark,os;print(os.path.dirname(pyspark.__file__))")/jars | grep hadoop-common`.
- Ler S3/MinIO (conector **S3A**): `spark.jars.packages=org.apache.hadoop:hadoop-aws:<versão do Hadoop>`
  (**case a versão!**) + configs `fs.s3a.endpoint`, `access.key`, `secret.key`,
  `path.style.access=true`, `connection.ssl.enabled=false`. Caminho com prefixo `s3a://`.
- **Primeira execução baixa os jars** do Maven (lenta, precisa de internet).
- Os vários `WARN` no boot (loopback address, native-hadoop) são **normais**.
- `df.rdd.getNumPartitions()` → quantas partições. Transformações são preguiçosas; `show()/count()/write()` disparam.

## Kafka
- Listar os topics: `docker compose exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list`.
- Inspecionar um topic (partições, réplicas, líder):
  `docker compose exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic <nome>`.
- Achar o diretório de log de um topic no broker:
  `docker compose exec kafka find / -type d -name "<topic>*" 2>/dev/null`.
- Testar consumo pelo terminal (sem escrever Python):
  `docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic <nome> --from-beginning`.
- Cliente Python: `pip install kafka-python` (`KafkaProducer`/`KafkaConsumer`). O `key=` da mensagem
  define a partição → **mesma chave = mesma partição = ordem preservada**.

## Mentalidade de debug (a mais importante de todas)
- **Prova, não chuta.** Rode um comando que mostre o estado real antes de agir.
- **Leia o erro literalmente** — a mensagem (e a URL/caminho nela) costuma entregar o problema
  (esquema dobrado, porta errada, chave no lugar errado).
- **Leia o traceback de baixo pra cima** — a última linha é o erro; logo acima, onde aconteceu.
- **`ERROR` no log nem sempre é erro seu** — pode ser falso positivo do grep ou aviso de ferramenta.
- **Inspecione o dado nas fronteiras** — `.shape`, `.dtypes`, `.head()`, `.isna().sum()`, `.duplicated().sum()`.
- **Conflito de porta? Use outra.** Não brigue.
- **Estado desejado ≠ real?** Recrie de verdade (`rm -sf` + `up`), não só `restart`.
- **Teste o comando na mão antes de automatizar** (cron, DAG) — 90% dos bugs aparecem aí.
