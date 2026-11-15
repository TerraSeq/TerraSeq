"""
Testes de configuracao.py e publicacao.py (o git e o e-mail são simulados:
nada é commitado, enviado ou publicado).

Rodar, na raiz do projeto:

    python3 -m unittest discover tests
"""
import contextlib
import io
import os
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import configuracao  # noqa: E402
import publicacao  # noqa: E402


class TestConfiguracao(unittest.TestCase):

    def test_link_padrao(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(configuracao.link_relatorio("REQ-1"), "https://TerraSeq.github.io/TerraSeq/reports/REQ-1/")

    def test_link_do_env(self):
        with mock.patch.dict(os.environ, {"GITHUB_REPO_OWNER": "outro", "GITHUB_REPO_NAME": "site"}):
            self.assertEqual(configuracao.link_relatorio("REQ-2"), "https://outro.github.io/site/reports/REQ-2/")

    def test_variavel_obrigatoria_faltando_encerra(self):
        with mock.patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()) as saida:
            with self.assertRaises(SystemExit):
                configuracao.obter_env_obrigatoria("NAO_EXISTE")
        self.assertIn("NAO_EXISTE", saida.getvalue())


class TestPublicarNoGithub(unittest.TestCase):

    def rodar(self, falhas=()):
        """Simula o git; 'falhas' = comandos (ex: ("push",)) que falham na 1ª vez."""
        chamadas, ja_falhou = [], set()

        def git(cmd, **kwargs):
            chamadas.append(cmd[1:])
            if cmd[1] in falhas and cmd[1] not in ja_falhou:
                ja_falhou.add(cmd[1])
                raise subprocess.CalledProcessError(1, cmd, output="", stderr="rejected")
            return mock.Mock(returncode=0)

        with mock.patch.object(publicacao.subprocess, "run", side_effect=git), \
             contextlib.redirect_stdout(io.StringIO()) as saida:
            publicacao.publicar_no_github("REQ-9")
        return chamadas, saida.getvalue()

    def test_caminho_feliz(self):
        chamadas, _ = self.rodar()
        self.assertEqual(chamadas, [
            ["add", "docs/dados/vitrine.json", "docs/reports/REQ-9"],
            ["commit", "-m", "Report REQ-9"],
            ["push"],
        ])

    def test_push_rejeitado_faz_pull_e_tenta_de_novo(self):
        chamadas, saida = self.rodar(falhas=("push",))
        self.assertEqual([c[0] for c in chamadas], ["add", "commit", "push", "pull", "push"])
        self.assertIn("Sincronizado", saida)

    def test_commit_falha_nao_tenta_push(self):
        chamadas, saida = self.rodar(falhas=("commit",))
        self.assertEqual([c[0] for c in chamadas], ["add", "commit"])
        self.assertIn("Erro ao commitar", saida)


class TestVitrineEEmail(unittest.TestCase):

    def test_erro_na_vitrine_nao_derruba(self):
        with mock.patch.object(publicacao.vitrine, "adicionar_analise", side_effect=OSError("disco cheio")), \
             contextlib.redirect_stdout(io.StringIO()) as saida:
            publicacao.atualizar_vitrine_html({}, "REQ-1")
        self.assertIn("Erro ao atualizar vitrine", saida.getvalue())

    def test_email_leva_o_link_do_relatorio(self):
        with mock.patch.dict(os.environ, {"GITHUB_REPO_OWNER": "TerraSeq", "GITHUB_REPO_NAME": "TerraSeq"}), \
             mock.patch.object(publicacao.notificacoes, "enviar_email_sucesso") as enviar:
            publicacao.enviar_email_notificacao("pesquisador@example.com", "REQ-5")
        enviar.assert_called_once_with("pesquisador@example.com", "REQ-5", "https://TerraSeq.github.io/TerraSeq/reports/REQ-5/")


class TestNomesIndefinidos(unittest.TestCase):
    """Pega nome usado e não importado (ex: 're' sem 'import re') antes de ir pro
    servidor. Precisa do pyflakes (pip install pyflakes); sem ele, o teste é pulado."""

    def test_sem_nomes_indefinidos(self):
        try:
            from pyflakes import api, reporter
        except ImportError:
            self.skipTest("pyflakes não instalado (pip install pyflakes)")
        raiz = os.path.join(os.path.dirname(__file__), "..")
        arquivos = [os.path.join(raiz, "src", f) for f in os.listdir(os.path.join(raiz, "src")) if f.endswith(".py")]
        arquivos += [os.path.join(raiz, f) for f in ("run_parse_blastn.py", "primer_blast_local.py")]
        saida = io.StringIO()
        api.checkRecursive(arquivos, reporter.Reporter(saida, saida))
        problemas = [linha for linha in saida.getvalue().splitlines() if "undefined name" in linha or "syntax" in linha.lower()]
        self.assertEqual(problemas, [])


if __name__ == "__main__":
    unittest.main()
