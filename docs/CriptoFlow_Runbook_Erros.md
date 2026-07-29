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
