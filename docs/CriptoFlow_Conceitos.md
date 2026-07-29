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

---

## Parte B — Dicionário de expressões

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

### Slowly Changing Dimension (SCD)
- **O que é:** técnica para lidar com atributos de dimensão que **mudam devagar ao longo do tempo**
  (ex.: nome ou categoria de uma moeda). As variações mais citadas:
  - *Tipo 1:* sobrescreve o valor antigo (não guarda histórico).
  - *Tipo 2:* nunca sobrescreve — fecha a linha antiga (preenchendo `valido_ate`) e insere uma nova
    marcada como atual, versionando a história com intervalos de validade. O dbt automatiza isso com *snapshots*.
- **O que avalia:** se você sabe **preservar histórico** numa dimensão em vez de apagá-lo. É
  conhecimento clássico de Kimball e cai bastante em entrevistas de modelagem. Saber quando usar
  Tipo 1 (não importa o histórico) vs. Tipo 2 (o histórico importa) é a parte que conta.

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
