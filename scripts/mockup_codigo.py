"""Gera o mockup de CÓDIGO de uma mudança a partir do diff real do git.

Convenção dos mockups do CriptoFlow: toda mudança gera dois, em HTML estático e sem JavaScript.
- RESULTADO: antes × depois do efeito (diagrama do pipeline, estado do DAG, amostra de dados),
  com dados reais. Feito à mão, no mesmo visual (tema escuro, sobretítulo verde, selo
  "dados reais · local", seções em cartões). Se a demonstração não pode alterar estado,
  simular numa transação desfeita (ou ambiente descartável) e dizer isso na página.
- CÓDIGO: gerado por este script a partir do diff real; só o porquê de cada trecho é escrito à mão.

Os dois ficam em `mockups/<issue>-<slug>/` (pasta LOCAL, no .gitignore: não sobe pro GitHub)
e são exibidos na página da tarefa no Notion, que é a cópia durável.

Uso (da raiz do repo; antes do commit, sempre com --estrito):
    python scripts/mockup_codigo.py mockups/<issue>-<slug>/codigo.yml [--estrito]

O código vem do git (`git diff <base>...<alvo>`); a config YAML traz só o
porquê de cada trecho. Saída: `codigo.html` ao lado da config — HTML estático,
CSS embutido, sem JavaScript.

Config (codigo.yml):
    titulo: "Bootstrap dos mockups"     # obrigatório
    issue: 30                           # opcional (vira link pro GitHub)
    base: main                          # opcional (padrão: main)
    alvo: HEAD                          # opcional (padrão: HEAD)
    resumo: |                           # opcional
      Uma frase sobre a mudança.
    trechos:
      - arquivo: scripts/exemplo.py
        ancora: "def parear"            # texto de uma linha ALTERADA do trecho
        porque: |
          Por que esse trecho existe.
      - arquivo: requirements.txt       # sem âncora = porquê do arquivo inteiro
        porque: |
          ...
"""
import argparse
import html
import re
import subprocess
import sys
from dataclasses import dataclass, field
from itertools import zip_longest
from pathlib import Path

import yaml
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_for_filename
from pygments.token import STANDARD_TYPES
from pygments.util import ClassNotFound

PASTA_MOCKUPS = "mockups"   # pasta local (no .gitignore); fora do diff mesmo se alguém forçar o add
CABECALHO_TRECHO = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@ ?(.*)$")
CHAVES_CONFIG = {"titulo", "issue", "base", "alvo", "resumo", "trechos"}
CHAVES_TRECHO = {"arquivo", "ancora", "porque"}


class ErroMockup(Exception):
    """Erro de config ou de git que impede gerar o mockup."""


# --- Modelo do diff: Arquivo -> Trecho -> Linha ----------------------------

@dataclass
class Linha:
    tipo: str                 # " " contexto, "-" removida, "+" adicionada
    texto: str
    num_antigo: int | None
    num_novo: int | None


@dataclass(eq=False)          # eq=False: comparação por identidade (dá pra usar como chave de dict)
class Trecho:
    inicio_antigo: int
    inicio_novo: int
    contexto: str             # o que o git mostra depois do @@ (ex.: a função)
    linhas: list = field(default_factory=list)

    def alteradas(self):
        return [linha for linha in self.linhas if linha.tipo != " "]

    @property
    def rotulo(self):
        return f"linhas -{self.inicio_antigo} +{self.inicio_novo}"


@dataclass(eq=False)
class Arquivo:
    antigo: str | None        # None = arquivo novo
    novo: str | None          # None = arquivo apagado
    trechos: list = field(default_factory=list)
    binario: bool = False
    # Preenchidos em coletar(): o arquivo inteiro, cru e realçado, antes e depois.
    plano_antigo: list = field(default_factory=list)
    plano_novo: list = field(default_factory=list)
    realce_antigo: list = field(default_factory=list)
    realce_novo: list = field(default_factory=list)

    @property
    def caminho(self):
        return self.novo or self.antigo

    @property
    def status(self):
        if self.antigo is None:
            return "novo"
        if self.novo is None:
            return "apagado"
        if self.antigo != self.novo:
            return "renomeado"
        return "alterado"


@dataclass
class Mudanca:
    arquivos: list
    ponto_base: str           # merge-base entre base e alvo (o "antes")
    alvo: str
    base_nome: str
    alvo_nome: str
    commits: list             # [(sha_curto, mensagem)]
    stat: str
    url_repo: str | None


# --- Leitura do diff --------------------------------------------------------

def _desaspar(caminho):
    """Desfaz as aspas que o git põe em caminhos com caracteres especiais."""
    caminho = caminho.rstrip("\t")          # o git põe TAB depois de caminhos com espaço
    if not (len(caminho) >= 2 and caminho[0] == caminho[-1] == '"'):
        return caminho
    escapes = {"n": b"\n", "t": b"\t", '"': b'"', "\\": b"\\", "a": b"\a",
               "b": b"\b", "f": b"\f", "r": b"\r", "v": b"\v"}
    corpo, saida, i = caminho[1:-1], bytearray(), 0
    while i < len(corpo):
        if corpo[i] == "\\" and i + 1 < len(corpo):
            if corpo[i + 1] in "01234567":   # octal: bytes UTF-8 de caracteres não-ASCII
                saida.append(int(corpo[i + 1:i + 4], 8))
                i += 4
                continue
            saida += escapes.get(corpo[i + 1], corpo[i + 1].encode())
            i += 2
            continue
        saida += corpo[i].encode()
        i += 1
    return saida.decode("utf-8", "replace")


def _sem_prefixo(caminho, prefixo):
    caminho = _desaspar(caminho)
    return caminho[len(prefixo):] if caminho.startswith(prefixo) else caminho


def _caminhos_do_cabecalho(linha):
    """'diff --git a/x b/y' -> ('x', 'y'). Só é usado quando não há linhas ---/+++."""
    resto = linha[len("diff --git "):]
    if resto.startswith('"'):
        fim = resto.index('" ', 1) + 1
        return _sem_prefixo(resto[:fim], "a/"), _sem_prefixo(resto[fim + 1:], "b/")
    antigo, _, novo = resto.partition(" b/")
    return _sem_prefixo(antigo, "a/"), novo


def ler_diff(texto):
    """Converte a saída do `git diff` (formato unified) em uma lista de Arquivos."""
    if texto.endswith("\n"):
        texto = texto[:-1]                  # senão a última linha vazia vira "contexto"
    arquivos, atual, trecho = [], None, None
    num_antigo = num_novo = 0

    for bruta in texto.split("\n"):         # split("\n"), não splitlines(): \r e \f fazem parte do código
        if bruta.startswith("diff --git "):
            atual, trecho = Arquivo(*_caminhos_do_cabecalho(bruta)), None
            arquivos.append(atual)
            continue
        if atual is None:
            continue

        cabecalho = CABECALHO_TRECHO.match(bruta)
        if cabecalho:
            num_antigo, num_novo = int(cabecalho[1]), int(cabecalho[2])
            trecho = Trecho(num_antigo, num_novo, cabecalho[3].strip())
            atual.trechos.append(trecho)
            continue

        if trecho is None:                  # ainda no cabeçalho do arquivo
            if bruta.startswith("new file mode"):
                atual.antigo = None
            elif bruta.startswith("deleted file mode"):
                atual.novo = None
            elif bruta.startswith("rename from "):
                atual.antigo = _desaspar(bruta[len("rename from "):])
            elif bruta.startswith("rename to "):
                atual.novo = _desaspar(bruta[len("rename to "):])
            elif bruta.startswith("--- "):
                atual.antigo = None if bruta == "--- /dev/null" else _sem_prefixo(bruta[4:], "a/")
            elif bruta.startswith("+++ "):
                atual.novo = None if bruta == "+++ /dev/null" else _sem_prefixo(bruta[4:], "b/")
            elif bruta.startswith("Binary files ") or bruta == "GIT binary patch":
                atual.binario = True
            continue

        if bruta.startswith("\\"):          # "\ No newline at end of file"
            continue
        tipo, conteudo = (bruta[0], bruta[1:]) if bruta else (" ", "")
        if tipo == "-":
            trecho.linhas.append(Linha("-", conteudo, num_antigo, None))
            num_antigo += 1
        elif tipo == "+":
            trecho.linhas.append(Linha("+", conteudo, None, num_novo))
            num_novo += 1
        else:
            trecho.linhas.append(Linha(" ", conteudo, num_antigo, num_novo))
            num_antigo += 1
            num_novo += 1
    return arquivos


def parear(trecho):
    """Alinha o trecho em pares (esquerda, direita) para a visão lado a lado.

    Contexto aparece dos dois lados. Um bloco de removidas seguido de um bloco
    de adicionadas é pareado linha a linha (como o "split view" do GitHub); a
    sobra fica com o outro lado vazio (None).
    """
    pares, removidas, adicionadas = [], [], []

    def descarregar():
        pares.extend(zip_longest(removidas, adicionadas))
        removidas.clear()
        adicionadas.clear()

    for linha in trecho.linhas:
        if linha.tipo == "-":
            if adicionadas:                 # "+" seguido de "-" fecha o bloco anterior
                descarregar()
            removidas.append(linha)
        elif linha.tipo == "+":
            adicionadas.append(linha)
        else:
            descarregar()
            pares.append((linha, linha))
    descarregar()
    return pares


# --- Realce de sintaxe ------------------------------------------------------

def _classe_css(tipo):
    while tipo not in STANDARD_TYPES:       # sobe até um tipo que o CSS do Pygments conhece
        tipo = tipo.parent
    return STANDARD_TYPES[tipo]


def realcar(conteudo, caminho):
    """Realça o arquivo inteiro e devolve o HTML de cada linha (índice 0 = linha 1).

    Realçar o arquivo todo (e não linha a linha) mantém o contexto do lexer:
    uma docstring de várias linhas continua com a cor de string.
    """
    try:
        lexer = get_lexer_for_filename(caminho, stripnl=False, ensurenl=False)
    except ClassNotFound:
        lexer = TextLexer(stripnl=False, ensurenl=False)
    linhas, atual = [], []
    for tipo, valor in lexer.get_tokens(conteudo):
        classe = _classe_css(tipo)
        for i, pedaco in enumerate(valor.split("\n")):
            if i:
                linhas.append("".join(atual))
                atual = []
            if pedaco:
                texto = html.escape(pedaco)
                atual.append(f'<span class="{classe}">{texto}</span>' if classe else texto)
    linhas.append("".join(atual))
    return linhas


# --- Git --------------------------------------------------------------------

def git(*args, raiz):
    # Lê bytes e decodifica na mão: com text=True o Python converte "\r" em "\n"
    # (universal newlines) e a numeração das linhas do diff sairia errada.
    resultado = subprocess.run(["git", "-c", "core.quotePath=false", *args],
                               cwd=raiz, capture_output=True)
    if resultado.returncode != 0:
        erro = resultado.stderr.decode("utf-8", "replace").strip()
        raise ErroMockup(f"git {' '.join(args)} falhou: {erro}")
    return resultado.stdout.decode("utf-8", "replace")


def _url_repo(raiz):
    """URL web do origin (sem credenciais), pra virar link de issue/commit."""
    try:
        remoto = git("remote", "get-url", "origin", raiz=raiz).strip()
    except ErroMockup:
        return None
    casou = re.match(r"^(?:https?://(?:[^@/]+@)?|git@)([^/:]+)[/:](.+?)(?:\.git)?/?$", remoto)
    return f"https://{casou[1]}/{casou[2]}" if casou else None


def coletar(base, alvo, raiz):
    """Lê do git tudo o que o mockup mostra: diff, arquivos inteiros, commits e stat."""
    ponto_base = git("merge-base", base, alvo, raiz=raiz).strip()
    filtro = ["--", ".", f":(exclude){PASTA_MOCKUPS}"]
    diff = git("diff", "--no-color", "--no-ext-diff", "-M", "--src-prefix=a/", "--dst-prefix=b/",
               ponto_base, alvo, *filtro, raiz=raiz)
    arquivos = ler_diff(diff)

    for arq in arquivos:
        if arq.binario:
            continue
        if arq.antigo:
            arq.plano_antigo = git("show", f"{ponto_base}:{arq.antigo}", raiz=raiz).split("\n")
            arq.realce_antigo = realcar("\n".join(arq.plano_antigo), arq.antigo)
        if arq.novo:
            arq.plano_novo = git("show", f"{alvo}:{arq.novo}", raiz=raiz).split("\n")
            arq.realce_novo = realcar("\n".join(arq.plano_novo), arq.novo)

    log = git("log", "--reverse", "--format=%h%x09%s", f"{ponto_base}..{alvo}", raiz=raiz)
    commits = [tuple(linha.split("\t", 1)) for linha in log.splitlines() if "\t" in linha]
    return Mudanca(
        arquivos=arquivos,
        ponto_base=git("rev-parse", "--short", ponto_base, raiz=raiz).strip(),
        alvo=git("rev-parse", "--short", alvo, raiz=raiz).strip(),
        base_nome=base,
        # Nome da branch; se o alvo for um SHA solto, o git devolve vazio e fica o próprio alvo.
        alvo_nome=git("rev-parse", "--abbrev-ref", alvo, raiz=raiz).strip() or alvo,
        commits=commits,
        stat=git("diff", "--stat", ponto_base, alvo, *filtro, raiz=raiz).rstrip(),
        url_repo=_url_repo(raiz),
    )


# --- Config e porquês -------------------------------------------------------

def carregar_config(caminho):
    """Lê e valida o codigo.yml. Chave desconhecida é erro (pega erro de digitação cedo)."""
    try:
        dados = yaml.safe_load(Path(caminho).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as erro:
        raise ErroMockup(f"não consegui ler a config {caminho}: {erro}") from erro
    if not isinstance(dados, dict):
        raise ErroMockup("a config precisa ser um mapa (chave: valor).")
    desconhecidas = set(dados) - CHAVES_CONFIG
    if desconhecidas:
        raise ErroMockup(f"chaves desconhecidas na config: {sorted(desconhecidas)}")
    if not dados.get("titulo"):
        raise ErroMockup("a config precisa de um 'titulo'.")
    if "issue" in dados and not isinstance(dados["issue"], int):
        raise ErroMockup("'issue' deve ser um número (ex.: issue: 30).")

    trechos = dados.get("trechos") or []
    for i, item in enumerate(trechos, 1):
        if not isinstance(item, dict):
            raise ErroMockup(f"trechos[{i}] precisa ser um mapa com 'arquivo' e 'porque'.")
        desconhecidas = set(item) - CHAVES_TRECHO
        if desconhecidas:
            raise ErroMockup(f"trechos[{i}]: chaves desconhecidas {sorted(desconhecidas)}")
        if not item.get("arquivo") or not item.get("porque"):
            raise ErroMockup(f"trechos[{i}] precisa de 'arquivo' e 'porque'.")
    dados["trechos"] = trechos
    dados.setdefault("base", "main")
    dados.setdefault("alvo", "HEAD")
    return dados


def atribuir_porques(arquivos, itens):
    """Liga cada trecho do diff ao seu porquê.

    Devolve (porques_de_arquivo, porques_de_trecho, avisos). Config que não bate
    com o diff (arquivo fora do diff, âncora sem par ou ambígua, porquê
    duplicado) é erro: sinal de que a config ficou desatualizada.
    """
    por_caminho = {}
    for arq in arquivos:
        for caminho in (arq.antigo, arq.novo):
            if caminho:
                por_caminho[caminho] = arq

    de_arquivo, de_trecho, erros = {}, {}, []
    for item in itens:
        arq = por_caminho.get(item["arquivo"])
        if arq is None:
            erros.append(f"'{item['arquivo']}' não está no diff.")
            continue
        ancora = item.get("ancora")
        if not ancora:
            if arq in de_arquivo:
                erros.append(f"{arq.caminho}: dois porquês para o arquivo inteiro.")
            de_arquivo[arq] = item["porque"]
            continue
        casados = [t for t in arq.trechos if any(ancora in linha.texto for linha in t.alteradas())]
        if not casados:
            erros.append(f"{arq.caminho}: a âncora {ancora!r} não aparece em nenhuma linha alterada.")
        elif len(casados) > 1:
            erros.append(f"{arq.caminho}: a âncora {ancora!r} é ambígua (aparece em {len(casados)} trechos).")
        elif casados[0] in de_trecho:
            erros.append(f"{arq.caminho}: dois porquês para o trecho {casados[0].rotulo}.")
        else:
            de_trecho[casados[0]] = item["porque"]
    if erros:
        raise ErroMockup("\n".join(erros))

    avisos = []
    for arq in arquivos:
        if arq in de_arquivo:
            continue
        if not arq.trechos:
            avisos.append(f"{arq.caminho}: arquivo sem porquê.")
        for trecho in arq.trechos:
            if trecho not in de_trecho:
                avisos.append(f"{arq.caminho} ({trecho.rotulo}): trecho sem porquê.")
    return de_arquivo, de_trecho, avisos


# --- HTML -------------------------------------------------------------------

# Visual padrão dos mockups do Larry: tema escuro, sobretítulo verde em caixa alta,
# seções em cartões, selo "dados reais" e etiquetas com contorno.
CSS = """
:root { --fundo:#0b0f17; --cartao:#111823; --codigo:#0d1117; --borda:#232c3a;
        --texto:#c9d1d9; --forte:#f0f6fc; --suave:#8b949e;
        --verde:#4ade80; --vermelho:#f47174; --azul:#58a6ff; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--fundo); color: var(--texto);
       font: 15px/1.6 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
a { color: var(--azul); }
strong { color: var(--forte); }
code, pre, table.codigo { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.pagina { max-width: 1320px; margin: 0 auto; padding: 32px 16px 48px; }
.sobretitulo { margin: 0; font-size: 13px; font-weight: 700; letter-spacing: .06em;
               text-transform: uppercase; color: var(--verde); }
.sobretitulo a { color: inherit; }
h1 { margin: 6px 0 14px; font-size: 30px; line-height: 1.25; color: var(--forte); }
h2 { margin: 32px 0 12px; font-size: 20px; color: var(--forte); overflow-wrap: anywhere; }
.intro p { margin: 0 0 8px; }
.meta { margin: 0; color: var(--suave); font-size: 14px; }
.selo { display: inline-block; margin-left: 6px; padding: 0 7px; border: 1px solid var(--verde);
        border-radius: 6px; color: var(--verde); font-size: 12px; font-weight: 700; white-space: nowrap; }
.etiqueta { display: inline-block; margin-left: 8px; padding: 1px 8px; border: 1px solid var(--suave);
            border-radius: 6px; font: 700 12px/1.5 system-ui, sans-serif; color: var(--suave);
            vertical-align: middle; }
.etiqueta-novo { border-color: var(--verde); color: var(--verde); background: rgba(74,222,128,.08); }
.etiqueta-apagado { border-color: var(--vermelho); color: var(--vermelho); background: rgba(244,113,116,.08); }
.etiqueta-renomeado, .etiqueta-alterado { border-color: var(--azul); color: var(--azul);
                                          background: rgba(88,166,255,.08); }
.cartao { background: var(--cartao); border: 1px solid var(--borda); border-radius: 12px;
          padding: 16px 18px; overflow: hidden; }
.cartao ul { margin: 0; padding-left: 20px; }
.rotulo { margin: 0 0 8px; font-size: 12px; font-weight: 700; letter-spacing: .06em;
          text-transform: uppercase; color: var(--verde); }
.stat { margin: 0; font-size: 13px; overflow-x: auto; color: var(--texto); }
.stat .mais { color: var(--verde); }
.stat .menos { color: var(--vermelho); }
.porque { margin: 0 0 14px; padding: 10px 14px; border-left: 3px solid var(--verde);
          border-radius: 4px; background: rgba(74,222,128,.06); }
.porque p, .porque ul { margin: 4px 0; }
.porque code, .intro code { padding: 0 4px; border-radius: 4px; background: rgba(110,118,129,.25);
                            color: var(--forte); font-size: .92em; }
.nota { margin: 0; color: var(--suave); font-style: italic; }
.trecho + .trecho { margin-top: 18px; padding-top: 18px; border-top: 1px solid var(--borda); }
.trecho-rotulo { margin: 0 0 8px; color: var(--suave); font: 12px ui-monospace, monospace; }
.rolagem { overflow-x: auto; border: 1px solid var(--borda); border-radius: 8px; }
table.codigo { width: 100%; min-width: 640px; border-collapse: collapse; table-layout: fixed;
               font-size: 13px; line-height: 1.5; background: var(--codigo); }
table.codigo col.num { width: 3.4em; }
table.codigo th { padding: 8px 10px; text-align: left; font: 600 13px system-ui, sans-serif;
                  color: var(--suave); border-bottom: 1px solid var(--borda); }
table.codigo td { padding: 0 10px; vertical-align: top; }
table.codigo td.num { padding: 0 8px; text-align: right; color: #6e7681; user-select: none; }
table.codigo td.cod { white-space: pre-wrap; overflow-wrap: anywhere; }
table.codigo td.cod:empty::after { content: " "; }
table.codigo th:nth-child(2), table.codigo td:nth-child(3) { border-left: 1px solid var(--borda); }
table.codigo td.removida { background: rgba(248,81,73,.13); }
table.codigo td.num.removida { background: rgba(248,81,73,.24); color: var(--vermelho); }
table.codigo td.adicionada { background: rgba(46,160,67,.15); }
table.codigo td.num.adicionada { background: rgba(46,160,67,.28); color: var(--verde); }
table.codigo td.vazio { background: repeating-linear-gradient(135deg, transparent 0 6px,
                        rgba(110,118,129,.08) 6px 12px); }
footer { margin-top: 36px; text-align: center; font-size: 12px; color: var(--suave); }
"""


def _inline(texto):
    texto = html.escape(texto)
    texto = re.sub(r"`([^`]+)`", r"<code>\1</code>", texto)
    return re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", texto)


def texto_rico(texto):
    """Formatação mínima do porquê: parágrafos, listas com '- ', `código` e **negrito**."""
    blocos = []
    for bloco in re.split(r"\n\s*\n", str(texto).strip()):
        linhas = [linha.strip() for linha in bloco.splitlines() if linha.strip()]
        if linhas and linhas[0].startswith("- "):
            itens = []
            for linha in linhas:
                if linha.startswith("- "):
                    itens.append(linha[2:])
                else:                       # continuação do item anterior
                    itens[-1] += " " + linha
            blocos.append("<ul>" + "".join(f"<li>{_inline(i)}</li>" for i in itens) + "</ul>")
        elif linhas:
            blocos.append(f"<p>{_inline(' '.join(linhas))}</p>")
    return "".join(blocos)


def _bloco_porque(texto):
    return f'<div class="porque"><p class="rotulo">Por quê</p>{texto_rico(texto)}</div>'


def _stat_colorido(stat):
    """Pinta os '+' de verde e os '-' de vermelho no gráfico do `git diff --stat`."""
    linhas = []
    for linha in html.escape(stat).splitlines():
        nome, barra, grafico = linha.rpartition(" | ")
        if barra:
            grafico = re.sub(r"(\++)", r'<span class="mais">\1</span>', grafico)
            grafico = re.sub(r"(-+)$", r'<span class="menos">\1</span>', grafico)
            linha = nome + barra + grafico
        linhas.append(linha)
    return "\n".join(linhas)


def _celulas(linha, lado, arq):
    if linha is None:
        return '<td class="num vazio"></td><td class="cod vazio"></td>'
    if lado == "antigo":
        num, plano, realce = linha.num_antigo, arq.plano_antigo, arq.realce_antigo
    else:
        num, plano, realce = linha.num_novo, arq.plano_novo, arq.realce_novo
    classe = {"-": "removida", "+": "adicionada", " ": "contexto"}[linha.tipo]
    # Só usa o realce se a linha do arquivo inteiro bate com a do diff; senão, texto puro.
    if num - 1 < min(len(plano), len(realce)) and plano[num - 1] == linha.texto:
        codigo = realce[num - 1]
    else:
        codigo = html.escape(linha.texto)
    return f'<td class="num {classe}">{num}</td><td class="cod {classe}">{codigo}</td>'


def _tabela(trecho, arq):
    linhas = "".join(
        f"<tr>{_celulas(esq, 'antigo', arq)}{_celulas(dir_, 'novo', arq)}</tr>"
        for esq, dir_ in parear(trecho)
    )
    return (
        '<div class="rolagem"><table class="codigo">'
        '<colgroup><col class="num"><col><col class="num"><col></colgroup>'
        '<thead><tr><th colspan="2">Antes</th><th colspan="2">Depois</th></tr></thead>'
        f"<tbody>{linhas}</tbody></table></div>"
    )


def _secao_arquivo(arq, de_arquivo, de_trecho):
    esc = html.escape
    etiqueta = f'<span class="etiqueta etiqueta-{arq.status}">{arq.status}</span>'
    titulo = f"<code>{esc(arq.caminho)}</code>"
    if arq.status == "renomeado":
        titulo = f"<code>{esc(arq.antigo)}</code> → <code>{esc(arq.novo)}</code>"
    partes = [f'<section><h2>{titulo}{etiqueta}</h2><div class="cartao">']
    if arq in de_arquivo:
        partes.append(_bloco_porque(de_arquivo[arq]))
    if arq.binario:
        partes.append('<p class="nota">Arquivo binário: sem visão de código.</p>')
    elif not arq.trechos:
        partes.append('<p class="nota">Sem mudança de conteúdo (só nome ou permissão).</p>')
    for trecho in arq.trechos:
        contexto = f" · {esc(trecho.contexto)}" if trecho.contexto else ""
        partes.append(f'<div class="trecho"><p class="trecho-rotulo">{trecho.rotulo}{contexto}</p>')
        if trecho in de_trecho:
            partes.append(_bloco_porque(de_trecho[trecho]))
        partes.append(_tabela(trecho, arq) + "</div>")
    partes.append("</div></section>")
    return "".join(partes)


def renderizar(cfg, mudanca, de_arquivo, de_trecho):
    esc = html.escape
    titulo = esc(str(cfg["titulo"]))
    url = mudanca.url_repo
    issue = cfg.get("issue")

    sobretitulo = ["CriptoFlow", "Mockup de código"]
    if issue is not None:
        sobretitulo.append(f'<a href="{esc(url)}/issues/{issue}">Issue #{issue}</a>' if url else f"Issue #{issue}")
    sobretitulo.append(f"branch {esc(mudanca.alvo_nome)}")

    adicionadas = sum(1 for a in mudanca.arquivos for t in a.trechos for l in t.linhas if l.tipo == "+")
    removidas = sum(1 for a in mudanca.arquivos for t in a.trechos for l in t.linhas if l.tipo == "-")
    meta = (f"<code>{esc(mudanca.ponto_base)}</code> (merge-base com <code>{esc(mudanca.base_nome)}</code>)"
            f" → <code>{esc(mudanca.alvo)}</code> · {len(mudanca.arquivos)} arquivo(s) · "
            f"<span style=\"color:var(--verde)\">+{adicionadas}</span> "
            f"<span style=\"color:var(--vermelho)\">−{removidas}</span>")

    selo = '<span class="selo">diff real · git</span>'
    resumo = texto_rico(cfg.get("resumo") or "O código abaixo vem direto do git; o porquê de cada trecho vem da config.")
    if resumo.endswith("</p>"):                 # o selo fecha o primeiro parágrafo, como no padrão
        resumo = resumo[:-4] + f" {selo}</p>"
    else:
        resumo += f"<p>{selo}</p>"

    commits = "".join(
        f"<li><code>{esc(sha)}</code> {esc(msg)}</li>" for sha, msg in mudanca.commits
    ) or "<li>(nenhum commit no intervalo)</li>"
    secoes = "".join(_secao_arquivo(arq, de_arquivo, de_trecho) for arq in mudanca.arquivos)
    estilo_realce = HtmlFormatter(style="github-dark").get_style_defs("table.codigo")

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mockup de código — {titulo}</title>
<style>{estilo_realce}{CSS}</style>
</head>
<body>
<div class="pagina">
<header>
<p class="sobretitulo">{" · ".join(sobretitulo)}</p>
<h1>{titulo}</h1>
<div class="intro">{resumo}</div>
<p class="meta">{meta}</p>
</header>
<main>
<section><h2>Commits</h2><div class="cartao"><ul>{commits}</ul></div></section>
<section><h2>Arquivos</h2><div class="cartao"><pre class="stat">{_stat_colorido(mudanca.stat) or "(sem mudanças)"}</pre></div></section>
{secoes}
</main>
<footer>Gerado por <code>scripts/mockup_codigo.py</code> a partir do diff real do git
(<code>{esc(mudanca.base_nome)}...{esc(mudanca.alvo)}</code>, sem <code>{PASTA_MOCKUPS}/</code>).
HTML estático, sem JavaScript.</footer>
</div>
</body>
</html>
"""


# --- CLI --------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,   # o --help mostra a convenção inteira
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", help="caminho do codigo.yml da mudança")
    parser.add_argument("--estrito", action="store_true",
                        help="falha (sem gerar HTML) se algum trecho alterado ficar sem porquê")
    parser.add_argument("--saida", help="HTML de saída (padrão: codigo.html ao lado da config)")
    args = parser.parse_args(argv)

    config = Path(args.config).resolve()
    saida = Path(args.saida).resolve() if args.saida else config.with_name("codigo.html")
    try:
        cfg = carregar_config(config)
        raiz = Path(git("rev-parse", "--show-toplevel", raiz=config.parent).strip())
        mudanca = coletar(cfg["base"], cfg["alvo"], raiz)
        de_arquivo, de_trecho, avisos = atribuir_porques(mudanca.arquivos, cfg["trechos"])
    except ErroMockup as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        return 1

    for aviso in avisos:
        print(f"AVISO: {aviso}", file=sys.stderr)
    if avisos and args.estrito:
        print("--estrito: há trecho sem porquê; nenhum HTML foi gerado.", file=sys.stderr)
        return 1

    saida.write_text(renderizar(cfg, mudanca, de_arquivo, de_trecho), encoding="utf-8")
    total_trechos = sum(len(arq.trechos) for arq in mudanca.arquivos)
    print(f"Mockup gerado: {saida} ({len(mudanca.arquivos)} arquivo(s), "
          f"{total_trechos} trecho(s), {len(avisos)} aviso(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
