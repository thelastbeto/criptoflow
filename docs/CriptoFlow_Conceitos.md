# CriptoFlow — Conceitos e Dicionário de Expressões

> Documento vivo de estudo. Duas partes:
> **A) Notas de conceito** — dúvidas discutidas ao longo do projeto, registradas com profundidade.
> **B) Dicionário de expressões** — termos novos, no formato *O que é* + *O que avalia* (o que a
> pergunta testa numa entrevista ou o que a escolha comunica na prática).
>
> Novos termos são adicionados em ordem alfabética. Última atualização: 2026-07-23.

---

## Parte A — Notas de conceito

### A.1 — Por que `id` é TEXT? Chave natural vs. chave substituta

**Contexto:** na tabela `mercado_bruto`, a coluna `id` é `TEXT` (ex.: `"bitcoin"`), com PK composta
`(id, coletado_em)`. Dúvida: um sequencial numérico não seria melhor?

**Por que TEXT:** o `id` não é nosso — vem da fonte. Na CoinGecko o identificador da moeda é uma
*string* (slug): `"bitcoin"`, `"ethereum"`. Guardamos como veio, e é com essa string que chamamos
outros endpoints (`/coins/{id}/market_chart`). Isso preserva a **rastreabilidade** até a origem.

**Chave natural vs. substituta:**
- *Chave natural (business key):* `"bitcoin"`. Vem de fora, tem significado no mundo real/na fonte.
- *Chave substituta (surrogate key):* `1, 2, 3...`, gerada pelo próprio banco (`SERIAL`/`IDENTITY`),
  sem significado externo.

**Por que o sequencial numérico seria ERRADO nesta tabela (raw/bronze):**
1. *Destruiria a idempotência.* Um `SERIAL` gera número novo a cada insert → o mesmo dado entraria como
   linhas distintas, e o `ON CONFLICT (id, coletado_em)` nunca detectaria conflito. A chave precisa ser
   **determinística** para deduplicar e reprocessar sem duplicar.
2. *Perderia o vínculo com a fonte.* Exigiria uma tabela extra mapeando número → moeda, sem ganho numa
   camada cujo trabalho é espelhar a origem.

**Onde o sequencial numérico está CERTO:** na modelagem dimensional (star schema, dbt — Parte II).
A dimensão `dim_moeda` deve usar uma **chave substituta inteira** (`moeda_sk`) como PK, mantendo
`"bitcoin"` como coluna de chave de negócio. Motivos:
- *Performance de join:* inteiros são menores e comparam mais rápido que strings (importa em fatos grandes).
- *Estabilidade:* se a fonte mudar o slug, a chave interna não muda e a mudança é versionada (ver SCD).

**Resposta madura (nível de entrevista):** a melhor chave *depende do papel da tabela*. Raw/bronze
espelha a fonte → chave natural TEXT. Dimensão modelada → chave substituta inteira + chave de negócio.

**Detalhe PostgreSQL:** `TEXT` e `VARCHAR(n)` têm desempenho idêntico no Postgres. O que pesa em join
não é TEXT vs VARCHAR — é TEXT vs INTEGER.

### A.2 — Tratamento de campos opcionais na ingestão com `.get()`

**Contexto:** ao transformar a resposta da API, campos obrigatórios usam colchetes (`m["id"]`) e
campos que podem faltar usam `.get()` (`m.get("price_change_percentage_24h")`).

- `m["chave"]` → se a chave **não existir**, o Python levanta `KeyError` e o pipeline quebra.
- `m.get("chave")` → se a chave não existir, devolve `None` (que vira `NULL` no banco), sem quebrar.
  Dá pra definir um padrão: `m.get("chave", 0)`.

**Por que importa:** fontes externas não garantem que todo campo venha em toda resposta (uma moeda
pode não ter `price_change_percentage_24h`). Usar `.get()` nos campos opcionais é **higiene de
ingestão**: a pipeline absorve a ausência em vez de falhar. Regra prática: colchetes para o que é
contratualmente obrigatório (e você *quer* que quebre se faltar), `.get()` para o que é opcional.

### A.3 — `%s` (parâmetros vinculados) para evitar SQL Injection

**Contexto:** na carga, os valores entram na query via placeholders `%s`, não por concatenação de
string. É o `psycopg2` (o driver) que substitui os `%s` de forma segura.

- **Errado:** `f"INSERT ... VALUES ('{valor}')"` — concatena o valor direto no texto do SQL.
- **Certo:** `cur.execute("INSERT ... VALUES (%s)", (valor,))` — o valor vai **separado** do comando.

**Por que importa (dois motivos):**
1. *Segurança:* concatenar permite **SQL Injection** — se `valor` contiver SQL malicioso (ex.:
   `'); DROP TABLE ...; --`), ele seria executado. Com `%s`, o driver trata o valor como *dado*,
   nunca como comando. É a defesa nº 1 e cai em entrevista.
2. *Correção:* valores com aspas, acentos ou tipos especiais (datas, `None`) são escapados
   corretamente pelo driver — você não precisa se preocupar com formatação manual.

**Observação:** o `%s` do psycopg2 **não** é o `%s` de formatação de string do Python. Nunca use
`%` ou f-string para montar SQL com dados — sempre passe os valores como segundo argumento.

### A.4 — `ON CONFLICT (chave) DO NOTHING` para idempotência

**Contexto:** a carga usa `INSERT ... ON CONFLICT (id, coletado_em) DO NOTHING`.

**O que faz:** ao tentar inserir uma linha cuja **chave já existe** (aqui, a PK composta
`(id, coletado_em)`), em vez de dar erro (`UniqueViolation`) ou duplicar, o Postgres simplesmente
**ignora** aquela linha e segue. É o "UPSERT" na variante "não faça nada se já existir".

**Por que importa:** torna a carga **idempotente** — reprocessar o mesmo lote não duplica nem
quebra. Como pipelines falham e são reexecutadas o tempo todo (retry, backfill), a carga precisa ser
segura contra reexecução. Variações úteis:
- `DO NOTHING` → mantém o registro antigo, ignora o novo.
- `DO UPDATE SET coluna = EXCLUDED.coluna` → atualiza o registro existente com os valores novos
  (UPSERT de verdade; útil quando o dado mais recente deve sobrescrever).

**Pré-requisito:** só funciona se houver uma **restrição de unicidade** (PK ou UNIQUE) na(s)
coluna(s) citada(s) no `ON CONFLICT`. Sem isso, não há conflito a detectar. Ver também: *Idempotência*
(Parte B) e *Granularidade* (a chave define o que conta como "mesma linha").

### A.5 — Consistência de snapshot: um timestamp único por execução lógica

**Contexto (caso real, Exercício 1):** ao paginar a coleta (5 páginas de 50 = 250 moedas), a função
`transformar` calculava `datetime.now()` **por página**. Resultado: cada página recebeu um
`coletado_em` ligeiramente diferente, fragmentando o que deveria ser *um só snapshot* em 5 instantes.

**Por que é um bug:** a granularidade pretendida é *uma moeda em um instante de coleta*. Se as 250
moedas de uma mesma coleta têm timestamps diferentes, a noção de "snapshot" se quebra. A consulta
clássica de último snapshot —
```sql
WHERE coletado_em = (SELECT max(coletado_em) FROM mercado_bruto)
```
— retornaria só a última página (50 moedas), não as 250. Métricas por snapshot ficam silenciosamente erradas.

**Correção:** calcular o instante **uma vez por execução lógica** e injetá-lo em toda a coleta:
```python
def transformar(bruto, coletado_em):
    return [(..., coletado_em) for m in bruto]

agora = datetime.now(timezone.utc)      # UM timestamp para toda a rodada
for p in range(1, 6):
    carregar(transformar(extrair_mercado(p=p), agora))
```

**Princípio geral:** o "carimbo de tempo" (e outros metadados de execução, como um `run_id`) deve ser
gerado **no início da execução** e propagado por todo o processamento daquela rodada — nunca recalculado
a cada etapa/lote. Isso mantém a coleta coerente e é pré-requisito para idempotência de verdade.

**Amarra três conceitos:** *Granularidade* (o que uma linha/snapshot representa) + *Idempotência*
(o timestamp fixo permite reexecução previsível) + *Consistência* (todos os registros de uma rodada
pertencem ao mesmo instante lógico). É resposta forte em entrevista sobre design de ingestão.

### A.6 — `DO NOTHING` vs `DO UPDATE`/`EXCLUDED`: uma decisão de SCD escondida

**Contexto (Exercício 2):** a tabela `moedas` (`id`, `nome`, `simbolo`) é, na prática, uma **dimensão**
— guarda a identidade descritiva de cada ativo. Ao carregá-la com `INSERT ... ON CONFLICT (id) ...`,
a cláusula que você escolhe **é** a estratégia de atualização da dimensão:

- **`ON CONFLICT (id) DO NOTHING`** → se a moeda já existe, ignora a nova versão. Se `nome`/`simbolo`
  mudarem na fonte, a tabela **não atualiza** e fica desatualizada. Comportamento tipo "congelado".
- **`ON CONFLICT (id) DO UPDATE SET nome = EXCLUDED.nome, simbolo = EXCLUDED.simbolo`** → sobrescreve
  com os valores novos. Mantém a dimensão sempre fresca, mas **apaga o histórico** do valor antigo.
  Isso é **SCD Tipo 1**.
- **SCD Tipo 2 (versionar histórico)** → não dá pra fazer só com `ON CONFLICT`; exige colunas de
  validade (`valido_de`, `valido_ate`, `atual`) e lógica de fechamento da linha antiga + inserção da
  nova. O dbt automatiza isso com *snapshots* (Parte II).

**`EXCLUDED`:** dentro do `DO UPDATE`, é a pseudo-tabela que representa a linha que *tentou* ser
inserida (os valores novos). `SET nome = EXCLUDED.nome` significa "use o valor que eu ia inserir".

**A lição:** escolher `DO NOTHING` ou `DO UPDATE` não é detalhe técnico — é decidir *se e como a
dimensão acompanha mudanças*. A pergunta que guia: **o histórico daquele atributo importa?** Não →
Tipo 1 (`DO NOTHING`/`DO UPDATE`). Sim → Tipo 2 (versionamento). Ver *SCD* e *UPSERT* na Parte B.

### A.7 — Tratamento de exceções: `except` específico, `from e` e o idioma `for...else`

**Contexto (Exercício 1):** um `try/except` foi adicionado à extração, mas com `except:` pelado
re-levantando uma mensagem genérica. Isso é anti-padrão. Três problemas:

1. **`except:` pelado captura demais.** Pega *qualquer* exceção — inclusive `KeyboardInterrupt`
   (Ctrl+C), `SystemExit` e bugs seus (`KeyError`, typos). Deve-se capturar **o tipo esperado**
   (ex.: `requests.RequestException`), deixando o inesperado subir.
2. **Perde a causa real.** `raise RuntimeError("mensagem genérica")` descarta o erro original. Se algo
   inesperado falha, você vê uma pista falsa. Use **encadeamento** com `from e` para preservar o traceback:
   ```python
   except requests.RequestException as e:
       raise RuntimeError(f"Falha de rede ao extrair: {e}") from e
   ```
3. **Mensagem semanticamente errada.** "Falha após várias tentativas" só deveria descrever
   esgotamento de retries — não qualquer falha.

**O idioma `for...else`:** o bloco `else` de um `for` executa **apenas se o laço terminar sem `break`**.
É o lugar idiomático para tratar "esgotou as tentativas":
```python
for t in range(tentativas):
    r = requests.get(...)
    if r.status_code == 429:
        time.sleep(2 ** t)
        continue
    r.raise_for_status()
    lote = r.json()      # só roda em resposta válida
    break
else:
    raise RuntimeError(f"Rate limit persistente após {tentativas} tentativas")
```
Sucesso → `break` (pula o `else`). Todas as tentativas falham (429 → `continue`) → o `for` termina
naturalmente → o `else` dispara o erro **preciso**.

**Bug relacionado que o `try/except` mascarava:** com o `raise` no `except`, o caso "todas as
tentativas deram 429" ficava sem tratamento, e o código caía em `r.json()` sobre uma resposta 429.
Mover o `lote = r.json()` para dentro do `for` (antes do `break`) e o `raise` para o `else` corrige.

**A lição:** *tratamento de erro que esconde o erro é pior que nenhum tratamento.* Capture o
específico, preserve a causa (`from e`), falhe barulhento no inesperado. (Detalhe de estilo: `break;`
com `;` funciona mas é ruído — em Python não se usa ponto-e-vírgula.)

### A.8 — Buffer em memória (`io.BytesIO` / `io.StringIO`)

**O que é:** um "arquivo falso" que vive na RAM, não no disco. Comporta-se como um arquivo aberto (tem
`.write()`, `.read()`, `.seek()`), mas os dados ficam na memória.

**Por que usar:** muitas libs escrevem/leem em "objetos tipo arquivo". Em vez de gerar um arquivo
temporário no disco (criar, ler, enviar, apagar), você gera o conteúdo direto na memória e envia pela
rede. No CriptoFlow: `df.to_parquet(buffer)` → `s3.put_object(Body=buffer.getvalue())` grava o Parquet
no MinIO **sem tocar o disco**.

**BytesIO vs. StringIO — qual usar:**
- **`io.BytesIO` → dados binários** (bytes). Use quando o formato é binário: Parquet, imagens
  (PNG/JPG), ZIP, gzip, XLSX, PDF. *Momentos ideais:* enviar um Parquet/arquivo pro S3 sem salvar em
  disco; gerar um ZIP em memória; processar bytes de um download.
- **`io.StringIO` → dados de texto** (str). Use quando o conteúdo é texto: CSV, JSON, TXT. *Momentos
  ideais:* montar um CSV em memória e ler com `pd.read_csv(StringIO(texto))`; capturar saída de texto
  de uma função; transformar uma string num "arquivo" pra uma lib que só aceita file object.

Regra rápida: **é binário? `BytesIO`. É texto? `StringIO`.**

**Sobre `seek(0)`:** ao escrever no buffer, o cursor fica no fim; `seek(0)` rebobina pro início.
Necessário se você passa o *buffer* pra algo ler; **redundante** se usa `buffer.getvalue()` (que retorna
todos os bytes independentemente do cursor).

### A.9 — Anatomia da camada silver (padrões de transformação)

A silver lê da bronze (lake → lake) e aplica cinco operações-chave:

- **Fan-in:** lista e concatena todos os Parquet da bronze num só DataFrame (`list_objects_v2` +
  `pd.concat`). Bronze acumula 1 arquivo por coleta; silver consolida.
- **Type casting com `errors="coerce"`:** `pd.to_numeric(col, errors="coerce")` converte o que dá e
  transforma lixo em `NaN`, em vez de derrubar o pipeline. É na silver que se garantem os tipos.
- **Deduplicação:** `sort_values` + `drop_duplicates(subset=chave, keep="last")` — o equivalente pandas
  do `ROW_NUMBER() ... = 1` do SQL. Garante uma linha por chave lógica `(id, coletado_em)`.
- **Padronização de schema:** `rename` traduz nomes da fonte (`current_price`) pros nomes limpos do
  domínio (`preco_usd`). O consumidor não precisa conhecer a fonte.
- **Overwrite idempotente:** chave de nome fixo por partição (`dia={dia}/mercado.parquet`) → rodar de
  novo sobrescreve, não acumula. A silver é 100% derivada e recomputável.

**Como debugar cada fronteira:** inspecione o dado com `.shape`, `.columns`, `.dtypes`, `.head()`,
`.isna().sum()`, `.duplicated().sum()`. Olhar o dado entre etapas resolve a maioria dos bugs.

### A.10 — Anatomia da camada gold (modelagem dimensional em código)

A gold lê da silver e monta o star schema: uma **dimensão** e um **fato**.

- **Construir a dimensão (`dim_moeda`):** selecionar só as colunas descritivas (`id`, `nome`, `simbolo`)
  → `drop_duplicates(subset=["id"])` para ter **uma linha por entidade** (a silver repete a moeda em cada
  snapshot) → `insert("moeda_sk", range(...))` para criar a **chave substituta** inteira. A dimensão
  responde "*quem* é a moeda".
- **Construir o fato (`fct_precos`):** `merge` (lookup) da silver com a dimensão pela chave de negócio
  `id`, para trazer a `moeda_sk` → selecionar **FK (`moeda_sk`) + granularidade (`coletado_em`) +
  métricas**. O fato NÃO repete nome/símbolo (isso mora na dimensão). O fato responde "*quanto*".
- **Testes de modelo (feitos na mão aqui, automatizados pelo dbt depois):**
  - *Uniqueness da dimensão:* `dim["id"].is_unique` deve ser `True` (sem moeda duplicada).
  - *Integridade referencial do fato:* `fct["moeda_sk"].isna().sum()` deve ser `0` (nenhum fato órfão).
- **Overwrite idempotente:** chaves fixas (`gold/dim_moeda/...`, `gold/fct_precos/...`) → reprocessar
  reconstrói a gold do zero, sempre igual.

**Ressalva de produção:** gerar a `moeda_sk` com `range()` a cada execução não é estável — se uma moeda
nova entra, as chaves podem mudar de posição. Num DW real a chave substituta é **persistente** (nunca
muda para uma entidade existente); é o que sustenta o SCD Tipo 2.

### A.11 — Fluxo de trabalho com Git + GitHub (feature branch + Pull Request)

**Conceito-base — três coisas diferentes:**
- **Git** = a ferramenta de versionamento (branches, commits, merge), roda na sua máquina. Não sabe o
  que é "Pull Request".
- **GitHub** = a plataforma (site) construída sobre o Git. O **Pull Request (PR)** é invenção dela: a
  tela de revisão + o gatilho do CI.
- **`gh`** = o GitHub CLI, o "controle remoto" da plataforma pelo terminal (cria/mergeia PR por comando).

**Início da etapa — sair da `main` atualizada e criar a branch:**
- `git checkout main` → volta pra branch principal.
- `git pull origin main` → atualiza a `main` local com o GitHub (não trabalhe em cima de código velho).
- `git checkout -b feat/nome-da-etapa` → cria **e** entra numa branch nova, partindo da `main`.

**Durante — trabalhar em commits pequenos:**
- `git add <arquivo>` → coloca o arquivo no *stage* (área do que vai no próximo commit).
- `git commit -m "feat: ..."` → registra um snapshot do stage, com mensagem.

**Fim — enviar, revisar e integrar:**
- `git push -u origin feat/nome-da-etapa` → envia a branch pro GitHub e vincula o *upstream* (`-u`).
- No GitHub: **New pull request** (base = `main`, compare = sua branch) → revisar o **diff** em
  "Files changed" → **Merge pull request** → **Confirm merge**.
- **Atenção:** `push` só *copia* a branch pro GitHub. O **merge** (o clique) é o passo separado que
  integra na `main`. Pushed ≠ merged.

**Limpeza — voltar limpo pra `main`:**
- `git checkout main` → volta pra principal.
- `git pull origin main` → traz o merge (feito no GitHub) pra `main` local; os arquivos da etapa reaparecem.
- `git branch -d feat/nome-da-etapa` → apaga a branch local já integrada (`-d` protege: só apaga se mergeada).
- `git fetch --prune` → remove a referência fantasma da branch remota já deletada.

**Convenção de nomes:** prefixo + kebab-case — `feat/`, `fix/`, `docs/`, `chore/`/`refactor/`. Ex.: `feat/camada-gold`.

### A.12 — Fundamentos do Airflow (orquestração e DAG)

**O que o Airflow resolve que o cron não resolve:** o cron só agenda ("rode tal comando em tal
horário"). O Airflow **orquestra**: além de agendar, gerencia **dependências** (só roda a próxima task
quando a anterior concluir com sucesso), **retry** (tenta de novo em falhas transitórias), **backfill**
(reprocessa datas passadas), **visibilidade** (interface web mostrando o que rodou/falhou) e **alertas**.

**DAG (Directed Acyclic Graph):** o modelo com que o Airflow representa a pipeline.
- *Directed (dirigido):* as setas têm direção → definem a ordem (bronze → silver → gold).
- *Acyclic (acíclico):* sem ciclos → nunca voltam pra trás, senão o pipeline rodaria em loop infinito.
- *Graph (grafo):* um conjunto de tarefas ligadas por essas setas.

**Task e dependências:** cada caixa do DAG é uma **task** (unidade de trabalho, tipicamente uma função
Python). A ordem é declarada com o operador `>>` — ex.: `bronze >> silver >> gold`. Se a `bronze` falha,
`silver` e `gold` nem tentam rodar.

**Modo `standalone`:** o modo "tudo em um" do Airflow para desenvolvimento — sobe agendador, interface
web e cria o usuário admin num container só. Em **produção**, esses componentes (scheduler, webserver,
banco de metadados) ficam separados e escalados.

**Como o código chega no Airflow:** todo arquivo `.py` colocado na pasta `dags/` (mapeada por volume) é
lido pelo Airflow e vira um DAG. Não se reescreve a lógica — envelopam-se as funções existentes
(`gravar_bronze`, etc.) em tasks.

### A.13 — Rede e volumes no Docker Compose

**Analogia do prédio de escritórios:** pense no `docker-compose` como um **prédio**. Cada serviço
(postgres, minio, airflow) é uma **sala**. Ao subir o compose, o Docker cria uma **rede privada** (o
prédio) e coloca todas as salas dentro dela.

**Rede — como os containers se enxergam:**
- Cada sala tem um **nome na porta = o nome do serviço**. O Docker roda um DNS interno (a "lista
  telefônica"), então de dentro do Airflow o MinIO é alcançável como `minio`.
- Entre salas, usa-se a **porta interna** do serviço, não a publicada. O MinIO escuta em `9000` dentro →
  outras salas usam `minio:9000`.
- **`localhost` dentro de um container = a própria sala** (loopback), nunca o host nem outra sala. Por
  isso `localhost:9100` quebra dentro do Airflow — não há MinIO na sala dele.
- Pra um container falar com **a sua máquina** (o host), existe o endereço `host.docker.internal`.

**Portas publicadas (`host:container`):** o mapeamento `9100:9000` é a "linha telefônica externa do
prédio pro mundo". Leitura: o lado **esquerdo (9100)** é a porta que **você** usa de fora (host); o lado
**direito (9000)** é a porta interna onde o serviço realmente escuta. Entre containers, só o lado direito
importa.

| Quem chama | Endereço do MinIO | Motivo |
|---|---|---|
| Host (você) | `localhost:9100` | porta publicada pro host |
| Container na mesma rede | `minio:9000` | nome do serviço + porta interna |
| Container → host | `host.docker.internal` | host visto de dentro |

**Volumes — dois tipos:**
- **Volume nomeado** (`pgdata:/var/...`): o lado esquerdo é um **nome**; o Docker cria e gerencia.
  **Precisa** ser declarado no bloco `volumes:` do topo. Use pra **dados** que devem persistir.
- **Bind mount** (`./dags:/opt/airflow/dags`): o lado esquerdo é um **caminho** de uma pasta real da sua
  máquina; mapeia direto. **Não** se declara. Use pra **código** que você edita e quer refletido na hora.
- Regra: **nome → volume nomeado (declara); caminho (`./`, `/`) → bind mount (não declara).**

### A.14 — Anatomia do `profiles.yml` do dbt (projeto × conexão, targets e segredos)

O dbt separa **o projeto** (o QUÊ — modelos SQL, versionados no Git) da **conexão** (o COMO — onde/como
conectar, com segredos). Essa separação vive em dois arquivos:
- `dbt_project.yml` (no repo) → configura o projeto; tem um campo `profile:` que aponta pro profile.
- `profiles.yml` (em `~/.dbt/`, **fora** do repo) → a conexão e as credenciais.

**Estrutura do `profiles.yml`:**
- **Nome do profile** (ex.: `criptoflow_dbt`) → deve bater com o `profile:` do `dbt_project.yml`. É a "cola".
- **`target`** → qual ambiente usar por padrão (ex.: `dev`). Permite `dev`/`prod`/`ci` isolados; troca
  com `--target`. Responde "como testar sem quebrar produção".
- **`outputs`** → o dicionário de ambientes; cada um é uma conexão.
- **`type`** → o adaptador/motor (`duckdb`, `postgres`, `snowflake`...).
- **`path`** (duckdb) → arquivo onde o dbt materializa os modelos.
- **`extensions` / `settings`** → extensões e comandos `SET` do DuckDB (ex.: `httpfs` + configs de S3) —
  o mesmo que se fazia na mão no `consultar.py`.

**Segurança (crítico):**
- O `profiles.yml` guarda **credenciais** → mora em `~/.dbt/`, **fora do repositório**. Nunca se commita.
- Se o `profiles.yml` estiver na pasta do projeto, **mova-o para `~/.dbt/`** (ou, se preferir mantê-lo
  no projeto, coloque-o no `.gitignore`).
- Ignore também os artefatos gerados: `*.duckdb`, `target/`, `dbt_packages/`, `logs/`.
- Regra: **só o código é versionado; segredos e artefatos gerados, nunca.**

### A.15 — O dbt na essência (staging, marts e materialização)

**Na essência:** no dbt você escreve só o `SELECT` (a lógica); o dbt cria o objeto no banco, **na ordem
certa** (via `ref()`), testa e documenta. É o mesmo que se fazia em pandas na silver/gold — só que
declarativo, versionado e testado.

**Materialização** — *como* o dbt persiste o resultado do `SELECT` (configurado por `+materialized:`):
- `view` → cria uma VIEW: consulta salva, recalcula a cada leitura, não guarda dado, leve de construir.
- `table` → cria uma TABLE: roda uma vez e grava o resultado; rápido de ler, precisa `dbt run` pra atualizar.
- É o view/table do banco — a novidade é que **o dbt cria pra você**.

**Camadas (convenção que espelha o Medallion):**
- **Staging** (`stg_*`): limpeza, uma por fonte (rename, cast, dedup básico). **Equivale à silver.** Geralmente `view`.
- **Marts** (`dim_*`, `fct_*`): consumo/negócio — o star schema, construído a partir do staging.
  **Equivale à gold.** Geralmente `table`.
- No dbt, **a config vem da PASTA**: modelos em `models/staging/` recebem a config de `staging:`; em
  `models/marts/`, a de `marts:`.

**A fronteira do dbt:** o dbt faz **só o "T"** do ELT. Não extrai de APIs nem pousa o cru (E/L) — começa
do dado que **já está** no lake. Ingestão (`bronze.py`) fica fora do dbt.

**Arquivos de config:** ver A.14 (`dbt_project.yml` = projeto; `profiles.yml` = conexão/segredos;
`schema.yml` = testes/docs).

### A.16 — Quando pandas × DuckDB/Polars × Spark (a métrica é a RAM)

**Métrica-mãe:** o dado (expandido em RAM, **com folga**) cabe na memória de uma máquina? O pandas
carrega **tudo na RAM**; o Spark **distribui** por várias máquinas.

**Comandos pra medir (decidir com número, não achismo):**
- `free -h` → RAM disponível.
- `du -sh pasta/` / `ls -lh arquivo.parquet` → tamanho do dado em disco.
- `df.memory_usage(deep=True).sum() / 1e9` → quanto um DataFrame ocupa em RAM (GB).
- `pyarrow.parquet.read_metadata("f.parquet").num_rows` → conta linhas **sem** carregar.

**Fator de expansão (crítico):** Parquet em disco é comprimido; em RAM ele "incha" ~**5 a 10×**, e as
operações (`join`, `groupBy`) criam cópias. Conta prática: **memória ≈ tamanho_parquet × ~7, com folga**.

**Faixas aproximadas (regra de bolso, variam com máquina/operações):**
- `< ~1 GB` → **pandas** (rápido, simples).
- `~1–10 GB` numa máquina boa → **DuckDB / Polars**.
- dezenas de GB a TBs, ou não cabe numa máquina → **Spark** (distribuído).

**O tier do meio que evita over-engineering:** não é binário pandas × Spark. **DuckDB** e **Polars** são
de **uma máquina só**, mas *out-of-core* (processam dado maior que a RAM) e muito mais rápidos que o
pandas. Escalada sã: **pandas → DuckDB/Polars → Spark**. Subir pro Spark cedo demais (cluster, infra,
custo) num problema que cabe numa máquina é over-engineering clássico.

**Sinal empírico:** rodou em pandas e deu `MemoryError`, ou a máquina começou a usar **swap** (lentíssimo,
visível no `free -h`/`htop`)? Passou do ponto do pandas — suba um degrau.

### A.17 — Como o Kafka guarda os dados (log, retenção, efêmero)

**O Kafka é um log append-only em disco.** Cada **topic** é dividido em **partições**; cada partição é
uma sequência de **segmentos** (arquivos `.log`) gravados no **diretório de log** do broker (config
`log.dirs`). Os eventos são anexados no fim — nunca alterados.

**Retenção — o dado NÃO fica pra sempre.** A config `log.retention.hours` (padrão **168h = 7 dias**),
`log.retention.ms` ou `log.retention.bytes` controlam quando os segmentos antigos são apagados.
Consumers conseguem ler (e reler) enquanto o dado está retido; passado o prazo, some.

**Durável × efêmero (no nosso caso):** o log é durável em disco **dentro do broker** — mas se o broker
roda num container **sem volume nomeado**, o dado do Kafka **some ao recriar o container**. No CriptoFlow
o destino durável de verdade é a **bronze** (o lake); o Kafka é um **buffer transitório**, então deixamos
efêmero de propósito no estudo. (Ver runbook: "Kafka efêmero".)

### A.18 — Resiliência em serviços de streaming (long-running)

Um produtor/consumidor de streaming **roda continuamente** (é um *serviço*, não um script batch). Por
isso ele **não pode morrer num erro transitório** da fonte (rate limit 429, timeout, queda de rede).

**A diferença batch × streaming:**
- *Batch* roda, termina e morre. Se falhar, você reexecuta (a idempotência cobre).
- *Streaming* precisa **ficar de pé** o tempo todo. Se cair a cada falha da fonte, não é serviço.

**O padrão de resiliência:** `try/except` **dentro do loop**, capturando exceção **específica**
(`requests.RequestException`); em falha, **loga e continua** na próxima iteração — nunca deixa a exceção
subir e matar o processo. Em **rate limit (429)**, aplica um **backoff maior** (esperar mais antes de
tentar de novo).

**Relaciona:** retry/backoff (ingestão da Parte I), `except` específico + `from e` (A.7), idempotência
(o consumer relê pelo offset sem duplicar).

### A.19 — Execução do Structured Streaming (micro-batches, triggers, output modes)

**Apesar da ideia de "tempo real", o Structured Streaming roda em micro-batches contínuos (*triggers*).**
Cada trigger processa o que chegou desde o anterior. **Sem dado novo → batch vazio** (não é erro).

**Trigger — de quanto em quanto tempo dispara:**
- Padrão: dispara **o mais rápido possível** → muitos batches vazios entre os dados.
- `trigger(processingTime="20 seconds")` → alinha à taxa do dado (menos ruído/custo).
- `availableNow` / `once` → processa o que há e **para** (útil pra rodar streaming como batch agendado).

**Output modes — O QUE é emitido a cada batch:**
- `append` → só linhas novas que não mudam mais (bom pra janelas já fechadas pelo watermark).
- `update` → só as janelas/linhas que **mudaram** naquele batch (o que usamos).
- `complete` → a tabela de resultado **inteira**, toda vez (caro; só pra agregações pequenas).

**`startingOffsets="earliest"`** → o 1º batch relê **todo o histórico** do topic (catch-up); depois só o novo.

**Batch parcial (só uma moeda):** com `update`, se os eventos de um poll caem em micro-batches
diferentes (timing do Kafka), a mesma janela é **atualizada aos pedaços** — não é duplicação nem backup.

---

## Parte B — Dicionário de expressões

### Airflow
- **O que é:** orquestrador de pipelines open-source. Modela o fluxo como um **DAG**, agenda, gerencia
  dependências, retries e backfill, e oferece uma UI de monitoramento. Padrão de mercado (alternativas:
  Dagster, Prefect, Mage).
- **O que avalia:** se você sabe **orquestrar** pipelines de verdade — dependências, confiabilidade e
  observabilidade — e não apenas "agendar um script". É a evolução natural do cron.

### Backfill
- **O que é:** rodar um pipeline para **datas/períodos do passado** — preencher dias que faltaram ou
  reprocessar o histórico com uma regra nova. O Airflow suporta nativamente porque cada execução é
  associada a uma data lógica.
- **O que avalia:** se você entende **reprocessamento histórico**. Conecta com o ELT (guardar o cru
  justamente pra poder reprocessar).

### Batch
- **O que é:** processamento de dados em **lotes**, em intervalos definidos (de hora em hora, diário
  às 6h). É o que o cron faz. Contrapõe-se ao streaming (evento a evento).
- **O que avalia:** se você escolhe a abordagem certa. A maior parte do mundo real é batch — mais
  simples, barato e suficiente. Streaming só quando a latência importa. Usar streaming onde batch
  bastava é over-engineering e conta *contra* você numa entrevista de arquitetura.

### Bind
- **O que é:** em redes, *bind* ("vincular") é o ato de um servidor **se associar a um endereço + porta**
  pra escutar conexões ali. "Bindar em `0.0.0.0:9092`" = escutar na porta 9092 em **todas** as interfaces
  de rede; "bindar em `localhost:9093`" = escutar só na interface **loopback** (interna).
- **O que avalia:** se você distingue **onde o servidor escuta (bind)** de **onde os clientes o encontram
  (advertise/connect)**. Aparece em erros como `bind: address already in use` (porta ocupada) e na config
  de *listeners* (Kafka, servidores web...).

### Código legado
- **O que é:** código que já fez parte do sistema mas foi substituído ou ficou dormente (ex.:
  `pipeline.py`, que gravava no Postgres, superado pelo data lake). Ainda existe, mas não está no fluxo ativo.
- **O que avalia:** se você **reconhece e sinaliza** código morto (comentário, pasta `legacy/`) em vez de
  deixá-lo confundir — ou de deletar sem critério. Num portfólio, legado sinalizado mostra evolução.

### Colunar
- **O que é:** forma de guardar dados **por coluna** em vez de por linha. Permite ler só as colunas
  necessárias de uma consulta e comprimir melhor (valores do mesmo tipo ficam juntos). Base do Parquet
  e dos warehouses OLAP. O oposto é *row-based* (OLTP), otimizado pra ler/gravar linhas inteiras.
- **O que avalia:** se você entende por que analytics usa formato colunar — menos I/O e melhor
  compressão — e por que OLTP transacional prefere linhas.

### Cron
- **O que é:** o agendador de tarefas do Linux. Lê uma tabela (a *crontab*) onde cada linha define
  **quando** rodar (5 campos de tempo) e **o que** rodar (um comando), e dispara em segundo plano na
  hora certa. Os 5 campos, em ordem: `minuto hora dia-do-mês mês dia-da-semana`, com `*` = "qualquer".
  Ex.: `0 * * * *` = no minuto 0 de toda hora; `0 6 * * *` = todo dia às 6h; `*/5 * * * *` = a cada 5 min.
  Comandos úteis: `crontab -e` (editar), `crontab -l` (listar). No WSL o serviço não sobe sozinho:
  `sudo service cron start`.
- **O que avalia:** se você entende **agendamento** e — mais importante — **por que orquestradores
  existem**. O cron só agenda: não tem retry, dependências entre tarefas, backfill, alertas,
  interface nem lineage. Saber quando o cron basta (job simples e isolado) vs. quando precisa de um
  orquestrador (Airflow) é a real pergunta de engenharia. No CriptoFlow, o cron é o "aperitivo" que a
  Parte II substitui por Airflow.
- **Armadilha clássica:** o cron roda num ambiente "pelado" (sem o `venv` ativo, começando na home).
  Por isso se usa **caminho absoluto** do binário do venv e `cd` para a pasta do projeto. Ver runbook.

### DAG
- **O que é:** *Directed Acyclic Graph* — grafo de tarefas com **direção** (define a ordem) e **sem
  ciclos** (sem loop). No Airflow, representa a pipeline: cada nó é uma **task**, cada seta uma
  **dependência**. Ex.: `bronze → silver → gold`.
- **O que avalia:** se você sabe modelar um pipeline como **dependências entre tarefas** — o vocabulário
  central de orquestração.

### Data Lake
- **O que é:** armazenamento de **arquivos** barato (object storage tipo Amazon S3 / MinIO) que guarda
  qualquer tipo de dado — cru, estruturado ou não. Flexível e baratíssimo, mas por si só não tem
  transações nem schema; sem governança vira um "pântano de dados".
- **O que avalia:** se você entende o papel do lake (guardar cru barato pra reprocessar depois) e os
  seus riscos. Contraste com data warehouse é pergunta clássica.

### Data Warehouse
- **O que é:** banco otimizado pra **análise** (OLAP), colunar e paralelo, com dado **estruturado e
  modelado** (star schema). Rápido de consultar, porém mais caro e rígido. Ex.: BigQuery, Snowflake, Redshift.
- **O que avalia:** se você distingue OLAP (análise) de OLTP (transação) e entende o papel do warehouse
  na entrega analítica, em contraste com o data lake.

### dbt (data build tool)
- **O que é:** ferramenta de transformação (o "T" do ELT). Você escreve modelos como `SELECT`s; o dbt
  materializa, ordena via `ref()`, testa e documenta. Padrão de mercado.
- **O que avalia:** se você faz transformação como engenharia de software (SQL versionado, testado, com
  lineage) e entende sua **fronteira** (não faz ingestão).

### DRY (Don't Repeat Yourself)
- **O que é:** princípio de engenharia de software que diz "não se repita" — cada pedaço de lógica
  deve existir em **um único lugar**. Em vez de copiar e colar o mesmo código, você o extrai para uma
  função/módulo e o **reaproveita**. No CriptoFlow, reusar `transformar` e `carregar` no laço de
  paginação (em vez de reescrevê-los) é DRY na prática.
- **O que avalia:** se você escreve código **manutenível**. Lógica duplicada é armadilha: quando a
  regra muda, você tem que lembrar de alterar em todos os lugares — e esquecer um gera bug silencioso.
  Centralizar em um ponto significa corrigir/evoluir uma vez só. É sinal de maturidade de engenharia,
  não só de "funciona".
- **Contraponto (honestidade técnica):** DRY levado ao extremo vira acoplamento — às vezes duas
  coisas *parecem* iguais mas evoluem por razões diferentes, e forçá-las na mesma função cria
  dependência ruim. A regra prática oposta é WET/"regra dos três": só abstraia quando a repetição
  realmente se confirmar (por volta da terceira vez). Saber *quando não* aplicar DRY também conta.

### Fan-in
- **O que é:** padrão em que **várias entradas convergem** para um único processamento — ex.: ler N
  arquivos Parquet e juntá-los num só DataFrame. É o "juntar".
- **O que avalia:** se você reconhece o padrão de consolidação (muitos → um), comum em transformações
  de lake e em joins/merges.

### Fan-out
- **O que é:** o inverso do fan-in — **uma origem se ramifica em várias saídas/tarefas** paralelas. Ex.:
  paginar uma API em N páginas, ou o *dynamic task mapping* do Airflow (uma task por moeda). É o "espalhar".
- **O que avalia:** se você pensa em **paralelismo e distribuição de trabalho** — quando dividir uma
  carga em várias unidades independentes.

### Fiddly
- **O que é:** adjetivo do inglês — algo **trabalhoso e cheio de detalhes pequenos, fácil de errar**,
  que exige atenção minuciosa pra acertar. Ex.: "a config do Kafka é *fiddly*" = tem muitos parâmetros e
  um errinho num deles já quebra.
- **Quando aparece:** costuma descrever setup/config com muitas peças interdependentes (Kafka, S3A,
  listeners, jars). Não é termo técnico — é vocabulário pra dizer "isso dá trabalho pra deixar redondo".

### Granularidade
- **O que é:** o nível de detalhe que uma linha da tabela representa — ou seja, "o que uma linha
  significa". Em `mercado_bruto`, a granularidade é *uma moeda em um instante de coleta*
  (definida pela chave `(id, coletado_em)`). Granularidade mais fina = mais detalhe e mais linhas;
  mais grossa = dado agregado.
- **O que avalia:** se você entende as consequências da escolha de nível de detalhe — capacidade de
  guardar histórico, risco de duplicação, e o que dá (ou não) pra agregar depois. Definir a
  granularidade *antes* de modelar é sinal de maturidade; é a primeira pergunta de qualquer tabela de fato.

### Idempotência
- **O que é:** propriedade de uma operação que, executada várias vezes, produz o mesmo resultado que
  executá-la uma vez — sem duplicar nem corromper. No CriptoFlow, o `ON CONFLICT (id, coletado_em)
  DO NOTHING` garante que reprocessar o mesmo lote não gera linhas duplicadas.
- **O que avalia:** se você projeta pipelines **confiáveis para reexecução**. Pipelines falham no meio
  e são rerodadas o tempo todo (backfill, retry, reprocessamento); o resultado precisa ser sempre
  consistente. É talvez o conceito mais central de confiabilidade em engenharia de dados.
- **Nota:** idempotência "pura" = mesma entrada → mesmo estado final. No v0 ela é parcial, porque o
  `coletado_em` muda a cada execução (cada rodada = novo snapshot, por design).

### Integridade referencial
- **O que é:** garantia de que toda **chave estrangeira (FK)** — ex.: a `moeda_sk` no fato — aponta para
  uma linha **existente** na tabela referenciada (a dimensão). Sem "órfãos".
- **O que avalia:** se você sabe validar a consistência entre fato e dimensão (nenhum FK nulo ou órfão).
  É o teste `relationships` do dbt e a base da confiabilidade de um modelo dimensional.

### Kimball
- **O que é:** Ralph Kimball, autor de *The Data Warehouse Toolkit*, referência clássica de
  **modelagem dimensional**. A abordagem Kimball organiza dados analíticos em *star schema*: uma
  tabela de **fato** central (métricas, ex.: preço/volume por moeda por instante) cercada de tabelas
  de **dimensão** (contexto descritivo, ex.: `dim_moeda`). Usa chaves substitutas nas dimensões e
  técnicas como SCD para versionar histórico. *(Acredito que seja referência muito citada; confirme
  a edição atual antes de citar formalmente.)*
- **O que avalia:** se você domina modelagem de data warehouse para analytics — fato vs. dimensão,
  star schema, chaves substitutas, desnormalização para leitura rápida. Cai muito em entrevistas de
  modelagem para vagas de pleno/sênior.

### Lakehouse
- **O que é:** arquitetura que une a **economia do data lake** (arquivos baratos em object storage) com
  as **garantias do data warehouse** (transações ACID, schema, time travel), via *table formats* como
  Apache Iceberg / Delta Lake. É a arquitetura que mais cresce no mercado.
- **O que avalia:** se você acompanha as arquiteturas atuais e sabe o problema que o lakehouse resolve —
  evitar a duplicação lake + warehouse e reduzir custo. Cai em entrevista de arquitetura sênior.

### Lookup
- **O que é:** operação de **buscar** um valor correspondente em outra tabela a partir de uma chave —
  ex.: dado o `id`, buscar a `moeda_sk` na dimensão. Na prática se faz com `merge`/`JOIN`. Também
  chamado de tabela "de-para".
- **O que avalia:** se você entende o padrão de **enriquecer ou traduzir** dados consultando uma tabela
  de referência (dimensão, de-para, mapeamento).

### Marts
- **O que é:** a camada de **consumo** do dbt — modelos de negócio (dimensões, fatos, agregados)
  construídos a partir do staging, prontos pra dashboards/análise. Equivale à gold. Geralmente `table`.
- **O que avalia:** se você entende a camada final modelada (star schema) e por que ela é separada e
  otimizada pra leitura.

### Materialização
- **O que é:** no dbt, como o resultado de um modelo é persistido — `view` (recalculada), `table`
  (gravada), e outras (`incremental`, `ephemeral`). Definida por `+materialized:`.
- **O que avalia:** se você escolhe a estratégia certa (view leve × table rápida) conforme o papel do
  modelo — trade-off custo/performance.

### Merge
- **O que é:** combinar dois DataFrames/tabelas **casando linhas por uma ou mais colunas-chave** — o
  equivalente pandas do `JOIN` do SQL (`df.merge(...)`). O parâmetro `how` (`left`, `right`, `inner`,
  `outer`) define **quais linhas sobrevivem**.
- **O que avalia:** se você domina joins — juntar dados de fontes diferentes por chave e escolher o tipo
  certo conforme o que precisa ser preservado. (Ex.: `how="left"` mantém tudo da esquerda.)

### Object Storage
- **O que é:** modelo de armazenamento que guarda dados como **objetos** (arquivo + metadados + um
  ID/chave único) num espaço plano organizado em *buckets*, acessível via API HTTP. Diferente de sistema
  de arquivos hierárquico. Escala de forma barata e praticamente "infinita". Ex.: Amazon S3, Google
  Cloud Storage, Azure Blob, MinIO.
- **O que avalia:** se você entende a base do data lake — por que object storage é barato e escalável,
  e por que ele não tem "pastas de verdade" (o que parece pasta são só prefixos no nome da chave).

### Orquestração
- **O que é:** coordenar **o que roda, quando e em que ordem**, com dependências entre tarefas, retries,
  agendamento, backfill, alertas e visibilidade. Ferramenta padrão: Apache Airflow (modela o pipeline
  como um DAG). O cron só agenda — a orquestração faz o resto. É uma das "correntes transversais".
- **O que avalia:** se você entende por que um orquestrador substitui o cron quando o pipeline cresce —
  dependências, confiabilidade e observabilidade.

### Overwrite
- **O que é:** estratégia de escrita que **substitui** o dado existente em vez de acrescentar (*append*).
  Em object storage, gravar com a **mesma chave** sobrescreve o objeto. Base de uma carga idempotente
  por *full refresh*.
- **O que avalia:** se você entende as estratégias de escrita (overwrite vs. append vs. upsert) e quando
  cada uma serve — overwrite para camadas recomputáveis; append para históricos brutos; upsert para
  atualizações incrementais.

### Parquet
- **O que é:** formato de arquivo **colunar e comprimido**, padrão de fato em analytics. Lê só as
  colunas necessárias e comprime bem. Usado no data lake no lugar de CSV/JSON.
- **O que avalia:** se você sabe por que não se usa CSV/JSON pra dado analítico em escala — economia de
  I/O e compressão. Relacionado: *Colunar*.

### Particionamento Hive
- **O que é:** convenção de organizar arquivos em "pastas" nomeadas no padrão `campo=valor` (ex.:
  `dia=2026-07-29/`), popularizada pelo Apache Hive. Ferramentas de consulta (Spark, DuckDB, Athena,
  Trino) reconhecem o padrão e tratam cada valor como uma **partição**.
- **O que avalia:** se você sabe estruturar um lake pra performance — o *partition pruning* (ler só as
  partições que o filtro pede) reduz I/O e custo. Relacionado: *Parquet*, FinOps.

### S3
- **O que é:** Amazon Simple Storage Service, o serviço de object storage da AWS (de 2006). Virou o
  **padrão de fato** — sua API é um "idioma comum" que outras ferramentas (MinIO, etc.) implementam.
  "Compatível com S3" significa que fala a mesma API.
- **O que avalia:** se você conhece o armazenamento mais usado em dados e entende o valor de "compatível
  com S3" — **portabilidade**: o mesmo código roda contra MinIO local ou S3 na nuvem.

### S3A
- **O que é:** o conector do Hadoop que ensina o Spark (e o ecossistema Hadoop) a ler/gravar em
  armazenamento compatível com S3 (S3 real, MinIO). Usa o prefixo `s3a://` e vem nos jars `hadoop-aws`
  (+ o AWS SDK, puxado como dependência).
- **O que avalia:** se você sabe conectar **processamento distribuído** ao object storage — e o cuidado
  crítico de **casar a versão do `hadoop-aws` com a versão do Hadoop embutida no Spark** (versão errada
  = `ClassNotFoundException`). É o análogo do `httpfs` do DuckDB, no mundo Spark.

### SDK
- **O que é:** *Software Development Kit* — conjunto de bibliotecas e ferramentas que uma plataforma
  oferece pra você programar contra ela sem lidar com o baixo nível (chamadas HTTP cruas, autenticação).
  O `boto3` é o SDK da AWS para Python.
- **O que avalia:** vocabulário de base — distinguir **SDK** (biblioteca pra desenvolver) de **API**
  (a interface que o SDK consome por baixo) e de **CLI** (ferramenta de linha de comando).

### Slowly Changing Dimension (SCD)
- **O que é:** técnica para lidar com atributos de dimensão que **mudam devagar ao longo do tempo**
  (ex.: nome ou categoria de uma moeda). As variações mais citadas:
  - *Tipo 1:* sobrescreve o valor antigo (não guarda histórico).
  - *Tipo 2:* nunca sobrescreve — fecha a linha antiga (preenchendo `valido_ate`) e insere uma nova
    marcada como atual, versionando a história com intervalos de validade. O dbt automatiza isso com *snapshots*.
- **O que avalia:** se você sabe **preservar histórico** numa dimensão em vez de apagá-lo. É
  conhecimento clássico de Kimball e cai bastante em entrevistas de modelagem. Saber quando usar
  Tipo 1 (não importa o histórico) vs. Tipo 2 (o histórico importa) é a parte que conta.

### Staging
- **O que é:** a camada de **limpeza** do dbt — um modelo por fonte (rename, cast, dedup básico),
  próximo do dado cru. Equivale à silver. Geralmente `view`.
- **O que avalia:** se você separa a limpeza (staging) da modelagem de negócio (marts) — organização em
  camadas, base de um projeto dbt sustentável.

### Star Schema (esquema estrela)
- **O que é:** o desenho central da modelagem dimensional (Kimball). Uma tabela de **fato** no meio,
  contendo as métricas mensuráveis (ex.: `preco_usd`, `volume_24h`) e as chaves estrangeiras para as
  dimensões, cercada por tabelas de **dimensão** que trazem o contexto descritivo (ex.: `dim_moeda`
  com nome, símbolo, categoria). Desenhado num diagrama, o fato no centro ligado às dimensões ao redor
  lembra uma estrela — daí o nome. As dimensões são **desnormalizadas** de propósito: repete-se
  informação para *ler rápido*, ao contrário do banco transacional (OLTP), que normaliza para
  *escrever rápido*.
- **O que avalia:** se você sabe modelar dados para **análise/BI** (OLAP), não só para transações.
  Entender fato vs. dimensão, por que desnormalizar na camada de consumo, e a diferença entre modelar
  para leitura (star schema) vs. para escrita (normalizado) é conhecimento de pleno e cai direto em
  entrevistas de modelagem. No CriptoFlow, o star schema é a camada *gold* que serve as análises.
- **Relacionados:** Kimball (a metodologia), Granularidade (o fato tem uma granularidade definida),
  SCD (como as dimensões versionam mudanças).

### Stream
- **O que é:** um *fluxo* de dados lido/escrito sequencialmente, aos poucos, em vez de tudo de uma vez
  na memória. Objetos "tipo arquivo" são streams (ex.: o `["Body"]` do `get_object`, que você lê com
  `.read()`). Permite processar dados grandes sem carregar tudo de uma vez.
- **O que avalia:** se você distingue *stream* (o fluxo/objeto de I/O) de *streaming* (o paradigma de
  processamento contínuo, evento a evento). São coisas diferentes com nomes parecidos.

### Streaming
- **O que é:** processamento **contínuo, evento a evento**, conforme os dados chegam (vs. batch, em
  lotes). Ferramentas: Apache Kafka, Spark Structured Streaming. Entra quando a **latência importa**
  (fraude, monitoramento em tempo real).
- **O que avalia:** se você sabe *quando* streaming se justifica (latência baixa) e quando é
  over-engineering. Entender *event time* vs. *processing time* e as garantias de entrega
  (at-most / at-least / exactly-once) é marca de senioridade.

### Topic
- **O que é:** o **canal nomeado** de eventos no Kafka — a categoria onde as mensagens do mesmo tipo vão
  (ex.: `precos-cripto`). Logicamente é um fluxo; fisicamente, é dividido em **partições** (diretórios com
  segmentos `.log` no broker). Producers **publicam** num topic; consumers **assinam** um topic.
- **O que avalia:** se você entende a unidade de organização do Kafka e sua relação com **partições**
  (paralelismo/ordem) e **retenção** (por quanto tempo o dado fica).

### UPSERT
- **O que é:** contração de **UP**DATE + IN**SERT** — uma operação de escrita que **insere** a linha se
  a chave não existe e **atualiza** (ou ignora) se já existe, tudo em um comando. No PostgreSQL é feito
  com `INSERT ... ON CONFLICT (chave) DO UPDATE ...` (atualiza) ou `... DO NOTHING` (ignora). A
  pseudo-tabela **`EXCLUDED`** carrega os valores que se tentou inserir, usada no `DO UPDATE SET
  coluna = EXCLUDED.coluna`.
- **O que avalia:** se você sabe fazer cargas **idempotentes** e lidar com dados que chegam repetidos
  ou atualizados sem duplicar nem estourar erro de chave. É a peça prática que sustenta a idempotência
  na camada de carga, e a escolha entre `DO NOTHING` e `DO UPDATE` conecta direto com SCD (como a
  dimensão trata mudanças). Cai em entrevista junto de idempotência e reprocessamento.
- **Cuidado:** exige uma restrição de unicidade (PK/UNIQUE) na coluna do `ON CONFLICT`. Sem ela, não
  há "conflito" a detectar e o comando falha.
