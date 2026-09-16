# CriptoFlow — Guia de Parâmetros (aprofundamento)

> Referência de **tuning e parametrização** por ferramenta. Diferente do **Manual de Configuração**
> (que é o "faça isto pra subir"), aqui a gente aprofunda: os parâmetros necessários, as **alternativas**
> e os **trade-offs** de cada escolha. Formato por ferramenta:
> *Config necessária → Parâmetros-chave → Alternativas/comportamentos → Trade-offs.*

---

# Docker Compose

## Config necessária (o que usamos no CriptoFlow)

O mínimo pra um serviço subir: `image`, e (conforme o caso) `ports`, `environment`, `volumes`, `command`.
Volumes **nomeados** também precisam ser declarados no bloco `volumes:` da raiz.

```yaml
services:
  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_KEY}
      MINIO_ROOT_PASSWORD: ${MINIO_SECRET}
    ports:
      - "9100:9000"
    volumes:
      - miniodata:/data
volumes:
  miniodata:
```

## Parâmetros-chave (os "botões")

| Parâmetro | O que faz | Quando/como usar |
|---|---|---|
| `image` | A imagem pronta a puxar do registry | Padrão. Sempre **pine a tag** (`postgres:16`), nunca `latest` em prod |
| `build` | Constrói a imagem a partir de um `Dockerfile` | Quando precisa de uma imagem **própria** (ex.: Airflow com libs já "assadas") |
| `command` | Sobrescreve o comando padrão da imagem | Ex.: `standalone` (Airflow), `server /data ...` (MinIO) |
| `ports` | Publica `host:container` | Só pro que o **host** precisa acessar. Esquerda = host, direita = interna |
| `expose` | Expõe a porta **só na rede interna** (sem publicar no host) | Quando só outros containers acessam |
| `environment` | Variáveis de ambiente (mapa ou lista) | Config + segredos via `${VAR}` (do `.env`) |
| `env_file` | Carrega um arquivo inteiro de env no container | Alternativa a listar cada `VAR` (ver abaixo) |
| `volumes` | Volume nomeado ou bind mount | Nomeado = dados persistentes; bind (`./x`) = código live |
| `depends_on` | Ordem de inicialização entre serviços | Controla **ordem**; readiness só com `condition: service_healthy` |
| `healthcheck` | Como o Docker sabe se o serviço está **saudável** | Habilita o `depends_on ... service_healthy` |
| `restart` | Política de reinício | `unless-stopped` pra serviços que devem ficar de pé |
| `user` | Roda o processo como `uid:gid` | `"1000:0"` no Airflow (permissão nos arquivos montados) |
| `networks` | Redes customizadas | Por padrão já vem uma rede do projeto; customize p/ isolar |
| `deploy.resources` | Limites de CPU/memória | Conter um serviço "faminto" (ex.: Spark, Airflow) |

## Decisões: Vantagens × Desvantagens

> Só entram aqui os parâmetros que são uma **bifurcação de verdade** — onde escolher A ou B muda algo.
> Parâmetro que você "usa e pronto" (ex.: `user`, `command`) fica só na tabela acima.
> Formato: **Parâmetro → cada valor possível → o que ganha (✅) e o que paga (❌)**.

---

### Parâmetro: `image` × `build`
*Valores possíveis: usar imagem pronta (`image`) ou construir a sua (`build` + Dockerfile).*

**Valor: `image` + `_PIP_ADDITIONAL_REQUIREMENTS`** (o que usamos hoje)
- ✅ Zero arquivo extra — só a linha no compose; começa a rodar na hora.
- ✅ Bom pra **prototipar**: mudou a lista de libs, é só editar e recriar.
- ❌ **Reinstala as libs a cada `--force-recreate`** → boot lento (a dor que você já sentiu).
- ❌ Não é reproduzível: a versão instalada depende de quando você subiu (sem lock).

**Valor: `build` (imagem própria com as libs "assadas")**
- ✅ Sobe em **segundos** — as libs já estão dentro da imagem.
- ✅ **Reproduzível**: a imagem é um artefato fixo (a lição do pyarrow, agora na infra).
- ✅ Ponto de portfólio: "tornei o ambiente reproduzível" é fala de quem manja de Docker.
- ❌ Exige manter um `Dockerfile` e **rebuildar** quando mudar dependência.
- ❌ Um passo a mais no setup de quem clona o repo (mas o `docker compose up` já builda sozinho).

---

### Parâmetro: `environment` (mapa) × `env_file`
*Valores possíveis: injetar segredo a segredo (`VAR: ${VAR}`) ou carregar o arquivo inteiro.*

**Valor: `environment` com `${VAR}`** (o que usamos hoje)
- ✅ **Controle fino**: o container só recebe o que você listou explicitamente.
- ✅ Fica **documentado no compose** o que cada serviço consome.
- ❌ **Repetitivo** quando são muitas variáveis (uma linha por segredo).

**Valor: `env_file: .env`**
- ✅ **Menos repetição** — uma linha carrega tudo.
- ❌ Joga **todas** as variáveis do `.env` no container, inclusive o que ele não precisa (superfície maior, menos explícito).
- ❌ Some a rastreabilidade: pra saber o que o serviço recebe, você tem que abrir o `.env`.

---

### Parâmetro: `depends_on` simples × com `healthcheck`
*Valores possíveis: garantir só a **ordem** de start, ou esperar a **prontidão** real.*

```yaml
  minio:
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]   # exemplo; o teste varia por imagem
      interval: 5s
      retries: 10
  airflow:
    depends_on:
      minio:
        condition: service_healthy
```

**Valor: `depends_on: [minio]` (simples)**
- ✅ Simples, uma linha.
- ❌ Garante que o MinIO **começou**, não que está **pronto** → o Airflow pode subir antes e dar **erro de conexão no boot** (a causa nº 1 desse erro).

**Valor: `depends_on: { condition: service_healthy }` + `healthcheck`**
- ✅ **Prontidão de verdade**: o dependente só sobe quando o outro responde.
- ✅ Mata na raiz o "erro de conexão no boot".
- ❌ Exige escrever o `healthcheck` certo (o `test` varia por imagem — descobrir o comando dá trabalho).
- ❌ Boot fica um pouco mais lento (espera o health passar) — mas é espera *saudável*.

---

### Parâmetro: `volumes` (tipo de volume)
*Valores possíveis: nomeado, bind mount ou tmpfs.*

**Valor: volume nomeado** (`miniodata:/data`)
- ✅ Docker gerencia, **persiste** entre recriações — ideal pra dado (MinIO, Postgres).
- ❌ Fica "escondido" na área do Docker; menos óbvio de inspecionar na mão.

**Valor: bind mount** (`./dags:/opt/airflow/dags`)
- ✅ **Código live**: edita no host, o container vê na hora (ótimo pra DAGs/scripts).
- ❌ Depende do caminho do host e de **permissão** (a dor do `user: "1000:0"`).

**Valor: tmpfs** (memória)
- ✅ Rápido e **some ao parar** — bom pra dado temporário/sensível.
- ❌ Volátil: reiniciou, perdeu. Não serve pra nada que precise durar.

---

### Parâmetro: `restart` (política de reinício)
*Valores possíveis: `no`, `on-failure`, `always`, `unless-stopped`.*

- **`no`** (padrão) → ✅ previsível, nada sobe sozinho; ❌ um crash derruba o serviço até você notar.
- **`on-failure`** → ✅ reinicia só se saiu com erro; ❌ não volta após um reboot da máquina.
- **`always`** → ✅ sempre de pé; ❌ sobe até quando você **quis** parar (chato em dev).
- **`unless-stopped`** → ✅ o meio-termo: recupera de crash/reboot, mas **respeita** quando você parou de propósito; ❌ ~nenhuma pra serviço (é por isso que é o mais comum).

## Trade-offs (o resumo de senior)

- **Publicar porta** só o necessário: cada `ports` é uma "porta pro mundo". O que é interno, deixe em `expose`.
- **`depends_on` sem healthcheck** te dá ordem, não prontidão — a causa nº 1 de "erro de conexão no boot".
- **`_PIP_ADDITIONAL_REQUIREMENTS` é dev**; imagem própria (`build`) é produção.
- **Pine as tags** das imagens (reprodutibilidade — a lição do pyarrow, agora na infra).
- **`user`** resolve permissão de volume montado, mas mexe em quem "é" o processo — use com o `:0` (grupo root) pra manter os arquivos internos graváveis.

### Melhorias possíveis no nosso compose (candidatas)
- Adicionar `healthcheck` no MinIO/Postgres e `depends_on: condition: service_healthy` no Airflow.
- Trocar `_PIP_ADDITIONAL_REQUIREMENTS` por uma **imagem própria** do Airflow (Dockerfile).
- Avaliar `env_file` pra reduzir a repetição de `${VAR}`.
