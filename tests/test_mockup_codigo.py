"""Testes do scripts/mockup_codigo.py (unittest, sem dependência extra).

Rodar da raiz do repo:
    python -m unittest -v
"""
import contextlib
import io
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import mockup_codigo as mc  # noqa: E402

DIFF_ALTERADO = textwrap.dedent("""\
    diff --git a/app.py b/app.py
    index 1111111..2222222 100644
    --- a/app.py
    +++ b/app.py
    @@ -1,5 +1,4 @@ def topo():
     import os
    -x = 1
    -y = 2
    +x = 10
     z = 3
     w = 4
    @@ -10,2 +9,3 @@ def baixo():
     a = 1
    +b = 2
     c = 3
    """)


DIFF_NOVO_LONGO = textwrap.dedent("""\
    diff --git a/novo.py b/novo.py
    new file mode 100644
    --- /dev/null
    +++ b/novo.py
    @@ -0,0 +1,5 @@
    +def a():
    +    return 1
    +
    +def b():
    +    return 2
    """)


def _linha(tipo, texto):
    return mc.Linha(tipo, texto, None, None)


class TestLerDiff(unittest.TestCase):

    def test_arquivo_alterado_com_varios_trechos(self):
        [arq] = mc.ler_diff(DIFF_ALTERADO)
        self.assertEqual(arq.status, "alterado")
        self.assertEqual(arq.caminho, "app.py")
        self.assertEqual(len(arq.trechos), 2)
        primeiro, segundo = arq.trechos
        self.assertEqual(primeiro.contexto, "def topo():")
        self.assertEqual(len(primeiro.linhas), 6)       # a última linha vazia do diff não vira contexto

        removida_y = primeiro.linhas[2]
        self.assertEqual((removida_y.tipo, removida_y.texto, removida_y.num_antigo), ("-", "y = 2", 3))
        adicionada = primeiro.linhas[3]
        self.assertEqual((adicionada.tipo, adicionada.num_novo), ("+", 2))
        contexto_z = primeiro.linhas[4]
        self.assertEqual((contexto_z.num_antigo, contexto_z.num_novo), (4, 3))
        self.assertEqual(segundo.alteradas()[0].num_novo, 10)

    def test_arquivo_novo(self):
        diff = textwrap.dedent("""\
            diff --git a/novo.py b/novo.py
            new file mode 100644
            index 0000000..3333333
            --- /dev/null
            +++ b/novo.py
            @@ -0,0 +1,2 @@
            +print("oi")
            +print("tchau")
            """)
        [arq] = mc.ler_diff(diff)
        self.assertEqual((arq.status, arq.antigo, arq.novo), ("novo", None, "novo.py"))
        self.assertEqual([l.num_novo for l in arq.trechos[0].linhas], [1, 2])

    def test_arquivo_apagado(self):
        diff = textwrap.dedent("""\
            diff --git a/velho.py b/velho.py
            deleted file mode 100644
            index 3333333..0000000
            --- a/velho.py
            +++ /dev/null
            @@ -1 +0,0 @@
            -print("adeus")
            """)
        [arq] = mc.ler_diff(diff)
        self.assertEqual((arq.status, arq.antigo, arq.novo), ("apagado", "velho.py", None))

    def test_renomeado_sem_mudanca_de_conteudo(self):
        diff = textwrap.dedent("""\
            diff --git a/antigo.py b/pasta/novo.py
            similarity index 100%
            rename from antigo.py
            rename to pasta/novo.py
            """)
        [arq] = mc.ler_diff(diff)
        self.assertEqual((arq.status, arq.antigo, arq.novo), ("renomeado", "antigo.py", "pasta/novo.py"))
        self.assertEqual(arq.trechos, [])

    def test_binario(self):
        diff = textwrap.dedent("""\
            diff --git a/logo.png b/logo.png
            new file mode 100644
            index 0000000..4444444
            Binary files /dev/null and b/logo.png differ
            """)
        [arq] = mc.ler_diff(diff)
        self.assertTrue(arq.binario)
        self.assertEqual(arq.caminho, "logo.png")

    def test_ignora_marcador_sem_newline_no_fim(self):
        diff = textwrap.dedent("""\
            diff --git a/a.txt b/a.txt
            --- a/a.txt
            +++ b/a.txt
            @@ -1 +1 @@
            -velho
            \\ No newline at end of file
            +novo
            \\ No newline at end of file
            """)
        [arq] = mc.ler_diff(diff)
        self.assertEqual([l.tipo for l in arq.trechos[0].linhas], ["-", "+"])

    def test_desaspar_caminho_com_acento(self):
        self.assertEqual(mc._desaspar('"a/ma\\303\\247\\303\\243.py"'), "a/maçã.py")
        self.assertEqual(mc._desaspar("a/simples.py\t"), "a/simples.py")


class TestParear(unittest.TestCase):

    def test_bloco_de_removidas_e_adicionadas(self):
        [arq] = mc.ler_diff(DIFF_ALTERADO)
        pares = [(e and e.texto, d and d.texto) for e, d in mc.parear(arq.trechos[0])]
        self.assertEqual(pares, [
            ("import os", "import os"),
            ("x = 1", "x = 10"),
            ("y = 2", None),
            ("z = 3", "z = 3"),
            ("w = 4", "w = 4"),
        ])

    def test_adicao_seguida_de_remocao_nao_se_mistura(self):
        trecho = mc.Trecho(1, 1, "", [_linha("+", "a"), _linha("-", "b")])
        pares = [(e and e.texto, d and d.texto) for e, d in mc.parear(trecho)]
        self.assertEqual(pares, [(None, "a"), ("b", None)])


class TestPorques(unittest.TestCase):

    def setUp(self):
        self.arquivos = mc.ler_diff(DIFF_ALTERADO)
        self.arq = self.arquivos[0]

    def test_ancora_e_porque_de_arquivo(self):
        itens = [
            {"arquivo": "app.py", "ancora": "x = 10", "porque": "mudou o x"},
            {"arquivo": "app.py", "porque": "vale pro resto"},
        ]
        de_arquivo, de_trecho, avisos = mc.atribuir_porques(self.arquivos, itens)
        self.assertEqual([p for _, p in de_trecho[self.arq.trechos[0]]], ["mudou o x"])
        self.assertEqual(de_arquivo[self.arq], "vale pro resto")
        self.assertEqual(avisos, [])

    def test_varias_ancoras_no_mesmo_trecho_viram_passeio_comentado(self):
        [novo] = mc.ler_diff(DIFF_NOVO_LONGO)
        itens = [  # fora de ordem de propósito: o script ordena pela linha
            {"arquivo": "novo.py", "ancora": "def b", "porque": "explica b"},
            {"arquivo": "novo.py", "ancora": "def a", "porque": "explica a"},
        ]
        _, de_trecho, avisos = mc.atribuir_porques([novo], itens)
        self.assertEqual([p for _, p in de_trecho[novo.trechos[0]]], ["explica a", "explica b"])
        self.assertEqual(avisos, [])

        mudanca = mc.Mudanca([novo], "aaa1111", "bbb2222", "main", "feat/x", [], "", None)
        saida = mc.renderizar({"titulo": "T"}, mudanca, {}, de_trecho)
        self.assertEqual(saida.count('class="porque-linha"'), 2)       # dentro da tabela...
        self.assertLess(saida.index("explica a"), saida.index("def a"))  # ...logo antes da linha
        self.assertLess(saida.index("def a"), saida.index("explica b"))
        self.assertLess(saida.index("explica b"), saida.index("def b"))

    def test_dois_porques_na_mesma_linha_e_erro(self):
        itens = [
            {"arquivo": "app.py", "ancora": "x = 10", "porque": "um"},
            {"arquivo": "app.py", "ancora": "x = 1", "porque": "dois"},
        ]
        # "x = 1" casa com "x = 1" (removida) e "x = 10" (adicionada): ambígua, então é erro.
        with self.assertRaisesRegex(mc.ErroMockup, "ambígua"):
            mc.atribuir_porques(self.arquivos, itens)
        itens[1]["ancora"] = "x = 10"
        with self.assertRaisesRegex(mc.ErroMockup, "mesma linha"):
            mc.atribuir_porques(self.arquivos, itens)

    def test_trecho_sem_porque_vira_aviso(self):
        itens = [{"arquivo": "app.py", "ancora": "b = 2", "porque": "novo b"}]
        _, _, avisos = mc.atribuir_porques(self.arquivos, itens)
        self.assertEqual(len(avisos), 1)
        self.assertIn("trecho sem porquê", avisos[0])

    def test_ancora_orfa_e_erro(self):
        itens = [{"arquivo": "app.py", "ancora": "nao existe", "porque": "?"}]
        with self.assertRaisesRegex(mc.ErroMockup, "não aparece"):
            mc.atribuir_porques(self.arquivos, itens)

    def test_ancora_so_casa_com_linha_alterada(self):
        # "import os" está no trecho, mas é contexto: não serve de âncora.
        itens = [{"arquivo": "app.py", "ancora": "import os", "porque": "?"}]
        with self.assertRaises(mc.ErroMockup):
            mc.atribuir_porques(self.arquivos, itens)

    def test_ancora_ambigua_e_erro(self):
        itens = [{"arquivo": "app.py", "ancora": " = ", "porque": "?"}]
        with self.assertRaisesRegex(mc.ErroMockup, "ambígua"):
            mc.atribuir_porques(self.arquivos, itens)

    def test_arquivo_fora_do_diff_e_erro(self):
        itens = [{"arquivo": "outro.py", "porque": "?"}]
        with self.assertRaisesRegex(mc.ErroMockup, "não está no diff"):
            mc.atribuir_porques(self.arquivos, itens)


class TestConfig(unittest.TestCase):

    def _config(self, texto):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        caminho = Path(pasta.name) / "codigo.yml"
        caminho.write_text(textwrap.dedent(texto), encoding="utf-8")
        return caminho

    def test_padroes_de_base_e_alvo(self):
        cfg = mc.carregar_config(self._config('titulo: "T"\n'))
        self.assertEqual((cfg["base"], cfg["alvo"], cfg["trechos"]), ("main", "HEAD", []))

    def test_chave_desconhecida_e_erro(self):
        caminho = self._config("""\
            titulo: "T"
            trechos:
              - arquivo: app.py
                ancoras: "x"
                porque: "erro de digitação em 'ancora'"
            """)
        with self.assertRaisesRegex(mc.ErroMockup, "ancoras"):
            mc.carregar_config(caminho)

    def test_sem_titulo_e_erro(self):
        with self.assertRaisesRegex(mc.ErroMockup, "titulo"):
            mc.carregar_config(self._config("issue: 1\n"))


class TestHtml(unittest.TestCase):

    def test_codigo_e_porque_sao_escapados(self):
        linha = mc.Linha("+", "<script>alert(1)</script>", None, 1)
        arq = mc.Arquivo("p.html", "p.html", [mc.Trecho(1, 1, "", [linha])])
        mudanca = mc.Mudanca([arq], "aaa1111", "bbb2222", "main", "feat/x", [], "", None)
        cfg = {"titulo": "<b>T</b>", "resumo": "**ok** `<i>`"}
        saida = mc.renderizar(cfg, mudanca, {arq: "porque <img src=x>"}, {})

        self.assertNotIn("<script", saida)          # nenhum JavaScript, nem vindo do diff
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", saida)
        self.assertNotIn("<img", saida)
        self.assertIn("&lt;b&gt;T&lt;/b&gt;", saida)
        self.assertIn("<strong>ok</strong> <code>&lt;i&gt;</code>", saida)

    def test_realce_escapa_e_preserva_numero_de_linhas(self):
        conteudo = 'x = "<b>"\n"""doc\nem duas linhas"""\n'
        linhas = mc.realcar(conteudo, "a.py")
        self.assertEqual(len(linhas), len(conteudo.split("\n")))
        self.assertNotIn("<b>", "".join(linhas))
        self.assertIn('class="s', linhas[2])        # a 2ª linha da docstring segue como string


class TestRepoTemporario(unittest.TestCase):
    """Ponta a ponta: um repo git de verdade, com branch, commit e config."""

    def _git(self, *args):
        subprocess.run(["git", "-c", "user.name=Teste", "-c", "user.email=teste@exemplo.com",
                        "-c", "commit.gpgsign=false", *args],
                       cwd=self.raiz, check=True, capture_output=True)

    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.raiz = Path(pasta.name)
        self._git("init", "-q")
        self._git("symbolic-ref", "HEAD", "refs/heads/main")
        # 20 linhas: mudar a 1ª e a última gera DOIS trechos (com 3 linhas de
        # contexto, mudanças próximas demais o git junta num trecho só).
        linhas = [f"v{i} = {i}" for i in range(1, 21)]
        (self.raiz / "app.py").write_text("\n".join(linhas) + "\n")
        self._git("add", ".")
        self._git("commit", "-q", "-m", "base")

        self._git("switch", "-q", "-c", "feat/x")
        linhas[0], linhas[-1] = "a = 10", "h = 80"
        (self.raiz / "app.py").write_text("\n".join(linhas) + "\n")
        self.pasta = self.raiz / "mockups" / "1-x"
        self.pasta.mkdir(parents=True)
        (self.pasta / "resultado.html").write_text("<p>resultado</p>\n")
        self._git("add", ".")
        self._git("commit", "-q", "-m", "muda a e h")

        self.config = self.pasta / "codigo.yml"
        self.config.write_text(textwrap.dedent("""\
            titulo: "Teste"
            issue: 1
            trechos:
              - arquivo: app.py
                ancora: "a = 10"
                porque: "Explica o a."
            """), encoding="utf-8")

    def _rodar(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
            codigo = mc.main([str(self.config), *args])
        return codigo, err.getvalue()

    def test_gera_html_e_exclui_a_pasta_de_mockups(self):
        codigo, err = self._rodar()
        self.assertEqual(codigo, 0)
        self.assertIn("trecho sem porquê", err)     # o trecho do "h" ficou sem porquê
        saida = (self.pasta / "codigo.html").read_text(encoding="utf-8")
        self.assertIn("app.py", saida)
        self.assertIn("Explica o a.", saida)
        self.assertIn("feat/x", saida)
        self.assertIn("muda a e h", saida)
        self.assertNotIn("resultado.html", saida)   # mockups/ fica fora do diff (mesmo commitado à força)

    def test_estrito_falha_sem_gerar_html(self):
        codigo, err = self._rodar("--estrito")
        self.assertEqual(codigo, 1)
        self.assertIn("--estrito", err)
        self.assertFalse((self.pasta / "codigo.html").exists())

    def test_estrito_passa_quando_todo_trecho_tem_porque(self):
        with self.config.open("a", encoding="utf-8") as f:
            f.write('  - arquivo: app.py\n    ancora: "h = 80"\n    porque: "Explica o h."\n')
        codigo, _ = self._rodar("--estrito")
        self.assertEqual(codigo, 0)
        self.assertTrue((self.pasta / "codigo.html").exists())


if __name__ == "__main__":
    unittest.main()
