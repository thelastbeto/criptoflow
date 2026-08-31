# CriptoFlow — Runbook de Erros e Soluções

> Documento vivo. Registra os erros enfrentados na construção do projeto e os erros
> comuns a antecipar em cada passo. Atualizado a cada etapa.
>
> **Formato de cada entrada:** Sintoma (mensagem) → Causa → Correção → Lição.
>
> Ambiente de referência: Windows + WSL2 (Ubuntu), Docker Desktop, Python 3.x, Postgres 16.
> Última atualização: 2026-07-23.

---

## Convenções

- Comandos rodam no **terminal do Ubuntu (WSL)**, não no PowerShell.
- No Ubuntu o interpretador é `python3` (e `pip3`), não `python`.
- O projeto vive em `~/projetos/criptoflow` (sistema de arquivos do Linux), **nunca** em `/mnt/c/...`.

---

## Passo 0 — Instalação e verificação das ferramentas

### Erros enfrentados
_(nenhum registrado — deu tudo certo)_

### Erros comuns a antecipar
- **`python: command not found` no WSL.** No Ubuntu o comando é `python3`. Se quiser digitar só `python`, instale `sudo apt install python-is-python3`.
- **`docker: command not found` dentro do WSL.** A integração WSL do Docker Desktop não está ligada.
  Correção: Docker Desktop → Settings → Resources → WSL Integration → ativar o toggle da distro Ubuntu → *Apply & Restart*.
- **"Add Python to PATH" desmarcado (no Windows).** Só afeta quem instala no Windows; no WSL não se aplica porque instalamos via `apt`.

---

## Passo 1 — Pasta do projeto, venv e Postgres no Docker

### Erros enfrentados

**1. YAML: `services.volumes additional properties 'pgdata' not allowed`**
- **Sintoma:** `docker compose up -d` falha na validação do `docker-compose.yml`.
- **Causa:** o bloco `volumes:` de nível raiz ficou **indentado dentro** de `services:`.
  Em YAML, indentação é hierarquia — recuo a mais faz o bloco "pertencer" ao serviço.
- **Correção:** o `volumes:` que **declara** o volume nomeado (`pgdata:`) tem que ficar colado
  na margem esquerda, como irmão de `services:`. O `volumes:` **dentro** do serviço (que monta
  o volume) é outro bloco, e esse fica indentado. Exemplo correto:
  ```yaml
  services:
    postgres:
      image: postgres:16
      # ...
      volumes:
        - pgdata:/var/lib/postgresql/data

  volumes:
    pgdata:
  ```
- **Lição:** YAML usa **2 espaços por nível e nunca Tab** (tabs são rejeitados). Existem dois
  blocos `volumes` distintos: um dentro do serviço (onde montar) e um na raiz (declarar o volume).

**2. IDE conecta e dá `FATAL: autenticação do tipo senha falhou para o usuário "criptoflow"`**
- **Sintoma:** o cliente gráfico (DBeaver) na porta 5432 recusa a senha, mesmo com credenciais
  aparentemente corretas.
- **Causa real (neste projeto):** já havia **outro Postgres** rodando na porta 5432 (banco `finances`).
  A conexão do host em `localhost:5432` batia no servidor errado, não no container do CriptoFlow.
- **Correção:** dar ao CriptoFlow uma porta de host própria — trocar o mapeamento para `"5433:5432"`,
  subir de novo (`docker compose up -d`) e apontar a IDE para a porta **5433**.
- **Lição 1 — conviver com vários Postgres:** rodar dois bancos ao mesmo tempo pede **uma porta de
  host distinta para cada projeto**. O container sempre escuta 5432 *internamente*; o que muda é a porta
  publicada no host (lado esquerdo do `host:container`).
- **Lição 2 — socket (trust) x TCP (senha):** `docker compose exec ... psql` conecta por *unix socket*
  local, que no pg_hba da imagem oficial é `trust` — **não valida senha**. A IDE conecta por **TCP**,
  que exige senha (`scram-sha-256`). Por isso o `psql` de dentro do container pode "funcionar" enquanto
  a IDE falha. Para reproduzir a checagem de senha dentro do container, force o TCP:
  `docker compose exec postgres psql -h 127.0.0.1 -U criptoflow -d criptoflow`.

### Erros comuns a antecipar
- **`Bind for 0.0.0.0:5432 failed: port is already allocated`.** Já existe algo usando a porta 5432
  (outro Postgres local ou container). Correção: parar o outro serviço, ou mapear outra porta no host,
  ex.: `- "5433:5432"` (e conectar via 5433).
- **`Cannot connect to the Docker daemon`.** O Docker Desktop não está aberto/rodando. Abra-o e espere ficar *Running*.
- **`password authentication failed for user "criptoflow"`.** Você alterou usuário/senha no compose
  depois que o volume `pgdata` já foi criado com as credenciais antigas. Correção (só em dev, apaga dados):
  `docker compose down -v` e suba de novo.
- **Esquecer de ativar o venv.** Instalou pacotes fora do `.venv` ou o script não acha `requests`.
  Sempre rode `source .venv/bin/activate` (prompt mostra `(.venv)`).
- **Editar YAML com Tab no `nano`.** Gera erro de indentação. Use espaços; no VS Code, a extensão de YAML avisa.

---

## Passo 2 — Primeira ingestão da API CoinGecko

### Erros comuns a antecipar
- **`ModuleNotFoundError: No module named 'requests'`.** O `venv` não está ativo ou o pacote não foi
  instalado nele. Rode `source .venv/bin/activate` e `pip install requests`.
- **`HTTP 429 Too Many Requests`.** Estourou o rate limit da CoinGecko. O `raise_for_status()` levanta
  a exceção; a versão com `time.sleep(2 ** t)` (backoff) resolve a maioria. Se persistir, espere e reduza a frequência.
- **`HTTP 401/403`.** Endpoint ou parâmetro exige chave/plano. Confirme o caminho em docs.coingecko.com.
- **Timeout / `ConnectionError`.** Rede ou API instável. O `timeout=30` evita travar; o retry cobre falhas transitórias.
- **`KeyError: 'price_change_percentage_24h'`.** Campo ausente para alguma moeda. Use `.get()` em vez de `[...]`.

## Passo 3 — Tabela + carga (ETL v0)

### Erros enfrentados

**1. `git push` falha com `error: src refspec main does not match any`**
- **Sintoma:** o push é recusado dizendo que não há `main` para empurrar.
- **Causa:** não existe branch chamado `main`. Ou o branch local se chama `master` (default do
  `git init` em versões antigas), ou não havia commit ainda.
- **Correção:** conferir com `git branch` e `git log --oneline`. Se o branch for `master`, renomear
  para `main` e empurrar: `git branch -M main` → `git push -u origin main`. Se não houver commit,
  commitar antes (`git add -A && git commit -m "..."`).
- **Efeito colateral inofensivo:** rodar `git remote add origin ...` duas vezes gera
  `error: remote origin already exists`. O origin já estava configurado; não precisa adicionar de novo
  (para trocar a URL, usar `git remote set-url origin <url>`).
- **Antecipação — autenticação:** push via HTTPS no GitHub não aceita a senha da conta; exige um
  *Personal Access Token* (PAT) no lugar da senha. Gerar em GitHub → Settings → Developer settings →
  Personal access tokens.

### Erros comuns a antecipar
- **`connection refused` / `could not connect to server` no psycopg2.** Porta errada. Neste projeto o
  host publica em **5433** (`"5433:5432"`), então o Python precisa de `port=5433`. O default do psycopg2 é 5432.
- **`relation "mercado_bruto" does not exist`.** A tabela não foi criada. Rode o `CREATE TABLE` no DBeaver antes.
- **`ImportError: cannot import name 'extrair_mercado'`.** `pipeline.py` e `extrair.py` precisam estar na
  **mesma pasta**, e o `extrair.py` não pode ter erro de sintaxe (é importado por inteiro).
- **`psycopg2.errors.UniqueViolation`.** Só ocorreria sem o `ON CONFLICT`; com `ON CONFLICT ... DO NOTHING`
  a carga é segura contra chave duplicada.
- **Dados não persistem após reiniciar o container.** Volume `pgdata` ausente/removido. Confira o bloco `volumes`.

### Nota conceitual
- **Idempotência aqui é parcial:** cada execução gera um `coletado_em` novo (novo snapshot, por design).
  O `ON CONFLICT` protege dentro da mesma coleta e em retentativas exatas do mesmo lote. Idempotência
  "pura" exigiria fixar o timestamp por execução lógica.

---

## Exercícios Parte I — Agendamento com cron (WSL)

### Erros enfrentados

**1. Log do cron cheio de `/bin/sh: 1: /home/.../criptoflow/: Permission denied`**
- **Sintoma:** o job roda mas o log só acumula "Permission denied" apontando para o diretório do projeto.
- **Causa:** o caminho do Python na linha do cron estava quebrado — havia um **espaço** e faltava o
  **ponto** do `.venv` (ficou `criptoflow/ venv/bin/python` em vez de `criptoflow/.venv/bin/python`).
  O shell interpretou `~/projetos/criptoflow/` (o diretório) como o **comando** a executar, e diretório
  não é executável → "Permission denied".
- **Correção:** corrigir o caminho para `.../.venv/bin/python` (grudado, com o ponto). Recomendado usar
  **caminho absoluto** para evitar ambiguidade de paste:
  ```
  */2 * * * * cd /home/betet/projetos/criptoflow && /home/betet/projetos/criptoflow/.venv/bin/python pipeline.py >> /home/betet/criptoflow.log 2>&1
  ```
- **Lição:** **"Permission denied" nem sempre é problema de permissão.** Pode significar "isso não é
  executável" (ex.: um diretório). Sempre veja *o que* o shell tentou executar. E **teste o comando
  inteiro na mão antes de pôr no cron** — 90% dos bugs de cron são caminho errado ou ambiente pelado.

### Erros comuns a antecipar
- **`crontab -e` abre o vim e você fica preso.** Escolha o **nano** (opção 1) no primeiro uso, ou rode
  `select-editor`. Sair do vim: `Esc` → `:q!` → Enter.
- **O job não dispara nunca (WSL).** O serviço do cron não sobe sozinho no WSL. Ligue com
  `sudo service cron start` (pode precisar reativar após reiniciar o Windows).
- **`ModuleNotFoundError` no cron mesmo funcionando no terminal.** O cron roda sem o `venv` ativo.
  Use o caminho absoluto do binário do venv (`.venv/bin/python`), nunca só `python3`.
- **Nada escrito no log.** Faltou o redirecionamento `>> arquivo.log 2>&1` (o `2>&1` captura os erros).
  Sem log, um job que falha às 3h fica invisível.

---

## Git / Versionamento — Branch duplicada (`main` + `master`)

### Erros enfrentados

**1. Repositório com duas branches (`main` e `master`) em paralelo**
- **Sintoma:** o GitHub mostra `main` e `master`; a `main` tem o código atual, a `master` ficou pra trás.
- **Causa:** o `git init` (em versões antigas) cria a branch `master`. Ao longo do caminho surgiu a
  `main` (via `git branch -M main` e/ou pelo padrão do GitHub), e as duas passaram a coexistir —
  commits/push acabaram indo pra branches diferentes.
- **Diagnóstico:**
  ```bash
  git fetch origin
  git branch -a                            # lista branches locais e remotas
  git log main..origin/master --oneline    # commits que existem só na master remota
  ```
  - `git branch -a` revelou: `main` (local), `origin/main` e `origin/master` (remotas) → **não havia
    `master` local**, só remota.
  - **Pegadinha:** `git log main..master` deu `fatal: ambiguous argument ... unknown revision`. Isso
    acontece quando um dos nomes **não existe como branch local**. Como a master era só remota, o certo
    é referenciá-la como `origin/master`.
- **Correção (após confirmar que a `origin/master` não tinha commit exclusivo):**
  ```bash
  # 1. No GitHub: Settings → Branches → Default branch → trocar para "main"
  #    (não dá pra apagar a branch padrão sem isso)
  # 2. Apagar a master remota:
  git push origin --delete master
  # 3. Limpar referências remotas mortas no local:
  git fetch --prune
  git branch -a                # deve sobrar só main e origin/main
  ```

### Lições
- **`main` ≠ `origin/main`:** uma é a branch local, a outra é a "foto" da branch no servidor.
  Confundi-las é fonte constante de erro. Ranges como `A..B` exigem que ambos os nomes existam no
  contexto (local ou com prefixo `origin/`).
- **Não se apaga a branch padrão:** defina outra como default no GitHub antes de deletar.
- **`git fetch --prune`:** ao apagar uma branch no servidor, o local mantém a referência fantasma
  (`remotes/origin/...`) até você podar. Sem `--prune`, o `git branch -a` engana.
- **Medir antes de cortar:** sempre cheque commits exclusivos (`git log main..origin/master`) antes de
  apagar qualquer branch.

### Erros comuns a antecipar
- **`git log A..B` com `unknown revision`:** um dos lados não existe como ref local. Use `git branch -a`
  e prefixe a remota com `origin/`.
- **`git push origin --delete master` recusado:** a master ainda é a branch padrão no GitHub. Troque o
  default primeiro.
- **Branch deletada continua aparecendo no `git branch -a`:** falta rodar `git fetch --prune`.
- **Commits exclusivos na branch a apagar:** se `git log main..origin/master` retornar commits, faça
  o merge para a `main` antes de deletar (`git merge origin/master`), para não perder trabalho.

---

## Parte II · Passo 1 — MinIO sobe mas o navegador/Python não acessa (portas não publicadas)

> **Resumo em uma linha:** o MinIO está "Up", mas `localhost:9001` não abre e o Python não conecta —
> porque as portas não foram publicadas no host. No Windows, isso quase sempre é faixa de porta
> reservada. **Solução rápida: use outra porta (91xx).**

### Como reconhecer (sintomas)
- No navegador, `http://localhost:9001` dá `ERR_INVALID_HTTP_RESPONSE` ou não carrega.
- `docker compose ps` mostra, na coluna PORTS do minio, `9000-9001/tcp` — **sem** o `0.0.0.0:...->...`
  que o postgres tem.
- Os containers estão rodando normalmente ("Up"), então não parece que quebrou nada.

### Solução rápida (se você só quer destravar)
Troque as portas do MinIO no `docker-compose.yml` por portas altas e livres:
```yaml
    ports:
      - "9100:9000"   # API S3 (é a que o Python usa)
      - "9101:9001"   # Console web (navegador)
```
**Salve o arquivo** (o Docker lê do disco, não do editor), recrie e valide:
```bash
docker compose up -d --force-recreate minio
docker port criptoflow-minio-1                          # deve listar 9000->9100 e 9001->9101
curl -I http://localhost:9100/minio/health/live         # deve responder "HTTP/1.1 200 OK"
```
Console passa a ser `http://localhost:9101`. Resolveu? Ótimo, siga a vida. Quer entender *por quê*? Continue.

### Diagnóstico passo a passo (árvore de decisão)
Rode os comandos **em ordem** e siga a seta conforme o resultado:

1. `docker compose config` → procure o bloco `minio: ports:`.
   - **Não aparecem as portas?** → o arquivo em disco está errado/não salvo. Corrija o YAML, salve, e recomece.
   - **Aparecem?** → a config está certa; o problema é o container. Vá ao passo 2.

2. `docker port criptoflow-minio-1` → lista o mapeamento real do container.
   - **Mostra `9000/tcp -> 0.0.0.0:9000`?** → está publicado! O problema é outro (ex.: firewall, navegador). Teste com `curl`.
   - **Vem vazio?** → o container não pegou as portas. Vá ao passo 3.

3. `docker compose rm -sf minio && docker compose up -d minio` → recria o container do zero (mantém os
   dados do volume). Rode `docker port` de novo.
   - **Agora publicou?** → era container defasado. Resolvido.
   - **Continua vazio, sem nenhum erro?** → é o caso da causa abaixo. Aplique a Solução rápida (troque a porta).

### Por que acontece (a causa)
Não é culpa sua nem do seu código. O Windows, às vezes, "tranca" faixas inteiras de portas para uso
interno (o sistema por trás do WSL2 e do Docker Desktop reserva essas faixas). A faixa dos 9000 costuma
cair numa dessas. Quando a porta está trancada, o Docker Desktop **não consegue publicá-la e, pior, não
avisa com erro** — ele só sobe o container sem a porta. Por isso o sintoma é tão confuso.

**Confirmar (opcional), no PowerShell** (não no WSL):
```powershell
netsh int ipv4 show excludedportrange protocol=tcp
```
Se 9000/9001 estiverem dentro de alguma faixa listada, é exatamente isso.

### Verificação final (como saber que consertou)
- `docker port criptoflow-minio-1` lista as duas portas mapeadas.
- `curl -I http://localhost:9100/minio/health/live` retorna `HTTP/1.1 200 OK`.
- `http://localhost:9101` abre o console do MinIO no navegador.

### Lições que ficam
- **EXPOSE ≠ publish:** `9000/tcp` é alcançável só dentro da rede Docker; `0.0.0.0:9000->9000` é
  mapeada pro host (o que o `ports:` faz).
- **Desejado ≠ real:** `docker compose config` mostra o que o compose QUER; `docker port`/`docker inspect`
  mostram o que o container TEM. Divergiu? Recrie com `rm -sf` + `up`, não só `restart`.
- **Docker lê do disco:** edição não salva no editor não existe pro Docker.
- **No Windows, publish falhar sem conflito de container = suspeite de porta reservada.** Não brigue:
  troque a porta.

---

## Git — trabalho "sumiu" ao trocar de branch (PR nunca foi mergeado)

> **Resumo em uma linha:** você fez o `push` da branch mas nunca criou/mergeou o PR; ao voltar pra
> `main`, o arquivo "desaparece" da pasta. Nada foi perdido — está na branch remota.
> **Solução rápida: crie e mergeie o PR no GitHub, depois `git pull`.**

### Como reconhecer (sintomas)
- `git pull` na `main` diz "Already up to date" mesmo depois de você achar que "subiu" o trabalho.
- `git log --oneline` da `main` **não mostra** o commit da etapa.
- `ls arquivo.py` → "No such file or directory" (sumiu da pasta ao trocar de branch).
- `git branch -a` ainda mostra `remotes/origin/feat/...` (o trabalho está lá, salvo).
- `git branch -d` avisou: *"merged to refs/remotes/origin/... but not yet merged to HEAD"*.

### Solução rápida
1. GitHub → aba **Pull requests** → **New pull request** (base = `main`, compare = `feat/...`).
2. Revisar o diff → **Merge pull request** → **Confirm merge** → (opcional) **Delete branch**.
3. No terminal: `git checkout main` → `git pull origin main` (o arquivo reaparece) → `git fetch --prune`.

### Árvore de decisão
- `git log` da `main` mostra o commit? **Sim** → está tudo certo, era só o warning. **Não** → siga.
- Aba Pull requests: **existe PR?**
  - **Não existe** → crie o PR e mergeie.
  - **Open** → mergeie.
  - **Merged**, mas a `main` local não tem → só falta `git pull origin main`.

### Por que acontece
`push` apenas copia a branch pro GitHub; o **merge** é um passo separado que integra na `main`. E o
`git branch -d` aceita apagar uma branch se ela bate com a **cópia remota** dela (upstream), mesmo sem
estar na `main` — por isso o warning "not yet merged to HEAD". Branch é uma cópia paralela do projeto:
ao trocar de branch, os arquivos visíveis mudam pra refletir aquela versão (nada se perde).

### Verificação final
- `git log --oneline -5` da `main` mostra o commit da etapa.
- `ls arquivo.py` → o arquivo está de volta.
- `git branch -a` (após `--prune`) mostra só a `main`.

### Lições que ficam
- **Pushed ≠ merged.** Enviar a branch não a integra na main; o merge é o clique separado.
- **Branch é cópia paralela**; trocar de branch troca os arquivos visíveis — não apaga nada.
- **Sempre confirme o merge antes de limpar** a branch (`git log` da main / aba Pull requests).

---

## Parte II · Passo 5 — DuckDB não conecta no MinIO (`Could not resolve hostname`)

> **Resumo em uma linha:** o `s3_endpoint` estava com `http://` e/ou na porta errada. Deve ser só
> `host:porta`, sem esquema, e na porta da **API S3 (9100)**, não a do console (9101).

### Como reconhecer (sintomas)
- `IOException: Could not resolve hostname error for HTTP HEAD to '...'`.
- A URL no erro mostra o esquema **dobrado** e/ou a porta do console: `http://http://...localhost%3A9101...`
  (o `%3A` é só o `:` codificado).

### Solução rápida
Na config do DuckDB, deixe o endpoint como `host:porta`, sem `http://`, na porta da API:
```python
con.execute("SET s3_endpoint='localhost:9100';")   # sem esquema; 9100 = API S3
```

### Árvore de decisão
- URL do erro tem `http://http://`? → você pôs `http://` no endpoint. **Tire** — o DuckDB adiciona o esquema sozinho.
- A porta é `9101`? → é a do **console** (navegador). Troque pra **`9100`** (API S3, por onde o código lê).
- Ainda falha? → confira `SET s3_use_ssl=false;` e `SET s3_url_style='path';` (MinIO local é http e path-style).

### Verificação final
- A query retorna os dados (ex.: as top 10 moedas) sem erro.

### Lições que ficam
- **Endpoint = `host:porta`** — o DuckDB (e a maioria dos clients S3) adiciona o esquema sozinho a
  partir do `s3_use_ssl`. Colocar `http://` no valor gera esquema dobrado.
- **9100 = API S3 (código); 9101 = console (navegador).** Ler/gravar dado vai pela API.
- **Leia a URL que o erro mostra** — ela entrega o problema (esquema dobrado + porta errada) de bandeja.

---

## Parte II · Passo 6 — pyarrow: `Repetition level histogram size mismatch` ao ler Parquet

> **Resumo:** versões diferentes de pyarrow no host e no container escreveram/leram o mesmo Parquet, e
> os metadados não bateram. **Solução rápida: pine a mesma versão nos dois e regenere os dados.**

### Como reconhecer (sintomas)
- `OSError: Repetition level histogram size mismatch` dentro de `pd.read_parquet`.
- O script **funciona no host** mas **quebra no container** (ou o contrário) — sinal de versões diferentes.

### Solução rápida
1. Confirme as versões: host → `python3 -c "import pyarrow; print(pyarrow.__version__)"`; container →
   `docker compose exec airflow python -c "import pyarrow; print(pyarrow.__version__)"`.
2. Pine a **mesma** versão nos dois: no `_PIP_ADDITIONAL_REQUIREMENTS` use `pyarrow==X.Y.Z` (a do host).
3. `docker compose up -d --force-recreate airflow`.
4. Apague as pastas `bronze/`, `silver/`, `gold/` no MinIO (dado escrito pela versão antiga) e reprocesse o DAG.

### Por que acontece
Os metadados do Parquet (ex.: o "repetition level histogram") não são 100% compatíveis entre versões do
pyarrow. A versão **leitora** não entendeu o que a **escritora** gravou. `_PIP_ADDITIONAL_REQUIREMENTS`
sem versão instala sempre a mais recente → diverge do host.

### Verificação final
- As versões (host e container) batem, e a DAG roda verde.

### Lições que ficam
- **Pine versões de dependências** — reprodutibilidade. Dependência sem versão fixa é bug esperando.
- Ambientes diferentes (host vs. container) instalam versões diferentes se você não fixar.

---

## Airflow — `Bad Request: The CSRF session token is missing` no login

> **Resumo:** cookie de sessão velho após recriar o container.
> **Solução rápida: aba anônima ou limpar cookies de `localhost:8080`.**

### Como reconhecer
- Tela "Bad Request — The CSRF session token is missing" ao logar, logo após um `--force-recreate` do Airflow.

### Solução rápida
1. Abra uma **aba anônima** (ou limpe os cookies de `localhost:8080`).
2. Pegue a senha nova (o standalone regenera a cada recriação):
   `docker compose exec airflow cat /opt/airflow/standalone_admin_password.txt`.
3. Logue com `admin` + a senha.

### Por que acontece
Recriar o container gera uma **chave secreta de sessão nova**; o cookie antigo do navegador fica inválido
→ o servidor não encontra um token CSRF válido. (Com metadados efêmeros, a senha de admin também muda a
cada recriação.)

### Lições que ficam
- Recriou o Airflow? Espere **senha nova** e **cookie velho inválido** — limpe o navegador.

---

## dbt docs serve — porta em uso + navegador não abre no WSL

> **Resumo:** o `dbt docs serve` tenta subir na porta **8080** (ocupada pelo Airflow) e tenta abrir um
> navegador que não existe no WSL. **Solução rápida: `--port 8081` e abrir a URL manualmente no Windows.**

### Como reconhecer
- `[Errno 98] Address already in use` ao rodar `dbt docs serve`.
- Vários `xdg-open: ... not found` / `no method available for opening 'http://localhost:8080'`.

### Solução rápida
```bash
dbt docs serve --port 8081
```
Depois abrir `http://localhost:8081` **no navegador do Windows** (o dbt não consegue abrir sozinho no WSL).

### Por que acontece
- **Porta em uso:** o Airflow já está na 8080; o `dbt docs serve` usa 8080 por padrão. Dois serviços,
  uma porta → conflito.
- **`xdg-open` sem navegador:** o WSL é um Linux sem navegador instalado, então nenhuma ferramenta Linux
  consegue "abrir o navegador" sozinha. Você abre a URL na mão, no Windows.

### Lições que ficam
- Conflito de porta = **escolha outra** (`--port`). Padrão que se repete (Postgres, MinIO, Airflow, dbt).
- Ferramentas Linux no WSL **não abrem navegador** — abra a URL manualmente no Windows.
- `dbt docs serve` **trava o terminal** (é um servidor em primeiro plano); saia com `Ctrl+C`.

---

## YAML — erros de indentação (hierarquia por espaços)

> **Resumo:** em YAML, **indentação é hierarquia**. Uma chave que vira "irmã" quando deveria ser "filha"
> (ou o contrário) quebra o parse. **Regra: cada nível de pertencimento = +2 espaços à direita; nunca Tab.**

### Como reconhecer (sintomas variam por ferramenta)
- Docker Compose: `services.volumes additional properties 'pgdata' not allowed`.
- dbt: `test definition dictionary must have exactly one key, got [... ] instead (2 keys)`.
- Em geral: erros de "propriedade não permitida", "chave duplicada", "esperava X e achou Y".

### A regra
- O que **pertence** a algo fica **recuado à direita** dele. Cada nível = **+2 espaços**. **Nunca use Tab**
  (YAML rejeita). No VS Code, a extensão de YAML aponta o erro na hora.

### Casos reais enfrentados
- **docker-compose:** o `volumes:` de nível raiz ficou indentado **dentro** de `services:` → virou
  propriedade de um serviço. Correção: `volumes:` na margem, **irmão** de `services:`.
- **dbt `schema.yml`:** o `arguments:` ficou no **mesmo nível** de `relationships:` (dois irmãos) →
  "2 keys". Correção: `arguments:` **dentro** de `relationships:` (+2 espaços), e `to`/`field` dentro de
  `arguments:`.

### Lições que ficam
- **Indentação = hierarquia.** Antes de mexer no valor, confira o **recuo**.
- **2 espaços por nível, nunca Tab.**
- **Leia o erro:** ele quase sempre diz *qual chave* está no lugar errado.

---

## Airflow demora a subir após `--force-recreate` (não é queda, é boot)

> **Resumo:** depois de recriar o container, o Airflow **reinstala as libs** do `_PIP_ADDITIONAL_REQUIREMENTS`
> (dbt-duckdb, pandas, pyarrow) e leva **minutos** pra subir. O `8080` fica fora do ar até terminar.
> **Solução rápida: esperar e confirmar a prontidão no log, não no navegador.**

### Como reconhecer
- `localhost:8080` dá `ERR_CONNECTION_RESET` / não carrega **logo após** um `docker compose up -d --force-recreate airflow`.
- O `docker compose ps` mostra o airflow como **`running`** (o container está de pé, mas o webserver ainda não).

### Solução rápida
```bash
docker compose logs airflow | grep -i "Airflow is ready"
```
- **Não apareceu ainda?** → ele ainda está instalando/subindo. Espere 2-3 min e rode de novo.
- **Apareceu?** → acesse o `8080` (senha nova: `docker compose exec airflow cat /opt/airflow/standalone_admin_password.txt`; use aba anônima pro CSRF).

### Por que acontece
O `_PIP_ADDITIONAL_REQUIREMENTS` **reinstala tudo a cada recriação** (é uma conveniência de desenvolvimento).
O webserver só sobe **depois** de instalar. Container `running` ≠ serviço `ready`.

### Solução definitiva (quando quiser robustez)
Assar as libs numa **imagem própria** (Dockerfile a partir do `apache/airflow`, com `pip install` no build)
em vez de reinstalar em runtime. Sobe em segundos e não reinstala nada.

### Lições que ficam
- **Container "running" ≠ serviço "ready".** Confirme a prontidão no **log** (`Airflow is ready`), não no navegador.
- Setup de dev (reinstalar em runtime) é frágil; produção usa imagem própria com deps já embutidas.

---

## Kafka (KRaft) — container sobe e morre: `advertised.listeners cannot use 0.0.0.0`

> **Resumo:** o container do Kafka morre no boot porque a validação recusa `0.0.0.0` como endereço
> anunciado. **Solução rápida: advertised = `localhost` (roteável); bindar o CONTROLLER em `localhost`.**

### Como reconhecer
- `docker compose ps -a` mostra o `kafka` como `Exited`.
- `docker compose logs kafka` termina com
  `IllegalArgumentException: ... advertised.listeners cannot use the nonroutable meta-address 0.0.0.0`.

### Conceito por trás
- `listeners` = onde o broker **binda/escuta** (`0.0.0.0` = todas as interfaces, **válido**).
- `advertised.listeners` = o endereço que o broker **anuncia** aos clientes (**tem que ser roteável**;
  `0.0.0.0` é recusado — não é um destino real que um cliente possa discar).

### Solução
```yaml
      KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092,CONTROLLER://localhost:9093
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
```
- Broker (PLAINTEXT) em `0.0.0.0` → pro Docker encaminhar a porta do host.
- Controller em `localhost` → só conversa internamente (bate com o quorum voter) e some o `0.0.0.0`
  que a validação rejeitava.
- Recriar: `docker compose up -d --force-recreate kafka` → conferir `Kafka Server started`.

### Lições que ficam
- **listeners (bind) ≠ advertised (anúncio).** `0.0.0.0` vale pra bind, não pra advertised.
- O **broker** precisa bindar `0.0.0.0` (pro Docker encaminhar); o **controller** só fala interno → `localhost`.
- Container que sobe e morre → `docker compose ps -a` + `docker compose logs`, não o output do `up`.

---

## Kafka — dados são efêmeros sem volume nomeado

> **Resumo:** sem um volume nomeado, o log do Kafka vive na camada gravável do container → **some** num
> `docker compose down`/recriação. Os eventos e offsets se perdem.

### Como reconhecer
- Depois de recriar/derrubar o container do Kafka, os eventos "sumiram"; um consumer com
  `auto_offset_reset="earliest"` relê a partir do vazio (o que havia antes se foi).

### Por que acontece
- O diretório de log (`log.dirs`) fica na **camada do container**, não persistido. Igual ao metadado
  efêmero do Airflow.

### Solução (quando quiser persistência)
- Fixar o log dir e montar um **volume nomeado**:
  ```yaml
  environment:
    KAFKA_LOG_DIRS: /var/lib/kafka/data
  volumes:
    - kafkadata:/var/lib/kafka/data
  ```
  e declarar `kafkadata:` no bloco `volumes:` do topo.

### Nota de arquitetura
- No CriptoFlow, deixamos o Kafka **efêmero de propósito**: o destino durável é a **bronze** (lake); o
  Kafka é só um **buffer transitório**. Persistir o Kafka faz sentido quando ele é a fonte da verdade.

### Lição que fica
- **Sem volume nomeado = dado efêmero.** Vale pra Kafka, metadado do Airflow, e qualquer container.

---

## Produtor Kafka morre com `429 Too Many Requests` da API

> **Resumo:** o produtor (serviço de longa duração) morria no **primeiro 429** porque o
> `raise_for_status()` levantava a exceção sem tratamento. **Solução: `try/except` dentro do loop +
> backoff no 429 + `continue`.**

### Como reconhecer
- Traceback com `requests.exceptions.HTTPError: 429 Client Error: Too Many Requests` e o produtor **para**.

### Por que acontece
- Chamada à API sem tratamento **dentro de um loop de longa duração**: qualquer 429/erro transitório
  derruba o serviço inteiro. Um serviço de streaming não pode morrer assim.

### Solução
1. **Espaçar** as chamadas (aumentar o `time.sleep`) para reduzir a frequência.
2. **Blindar o loop:**
   ```python
   while True:
       try:
           r = requests.get(...)
           if r.status_code == 429:
               time.sleep(60)      # backoff maior no rate limit
               continue
           r.raise_for_status()
           # ... publica ...
       except requests.RequestException as e:
           print(f"erro transitorio: {e} — continuando")
       time.sleep(20)
   ```

### Nota de arquitetura
- A CoinGecko **não é streaming real** (é polling com rate limit). Rode em **rajadas**, não 24/7 (teto
  mensal do plano grátis ~10k chamadas). Streaming de verdade seria um WebSocket de corretora.

### Lições que ficam
- **Serviço de streaming não pode morrer em erro transitório** — `try/except` específico dentro do loop, log + `continue`.
- **429 pede backoff maior** que um erro comum.
