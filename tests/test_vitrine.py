"""
Testes da lista da vitrine (src/vitrine.py). Usam um arquivo temporário:
a vitrine de verdade (docs/dados/vitrine.json) não é tocada.

Rodar, na raiz do projeto:

    python3 -m unittest discover tests
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import vitrine  # noqa: E402

PEDIDO = {"Primer forward": " acgt ", "Primer reverse": "ggcc", "Região alvo": "ITS", "Banco de Dados": "fungi"}
RESULTADO = {"primers": {"pair_name": "ITS1/ITS4"}, "summary": {"mean_amplicon_size": 612.6}}


class TestVitrine(unittest.TestCase):

    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.caminho = os.path.join(self.pasta.name, "vitrine.json")

    def tearDown(self):
        self.pasta.cleanup()

    def adicionar(self, req, req_id, resultado=None):
        with contextlib.redirect_stdout(io.StringIO()):     # sem os prints do pipeline no teste
            return vitrine.adicionar_analise(req, req_id, resultado, self.caminho)

    def test_montar_entrada(self):
        entrada = vitrine.montar_entrada(PEDIDO, "REQ-1", RESULTADO, data=datetime(2026, 11, 15))
        self.assertEqual(entrada, {
            "id": "REQ-1", "nome_par": "ITS1/ITS4", "alvo": "ITS", "banco": "Fungi",
            "forward": "ACGT", "reverse": "GGCC", "amplicon_bp": 613, "data": "2026-11-15",
        })

    def test_sem_resultado(self):
        entrada = vitrine.montar_entrada({"Banco de Dados": "Banco_Novo"}, "REQ-2")
        self.assertEqual(entrada["amplicon_bp"], 0)
        self.assertEqual(entrada["nome_par"], "Par Não informada")
        self.assertEqual(entrada["banco"], "Banco_Novo")      # banco não mapeado fica como veio

    def test_adicionar_e_ler(self):
        self.adicionar(PEDIDO, "REQ-1", RESULTADO)
        self.adicionar(PEDIDO, "REQ-2")
        self.assertEqual([a["id"] for a in vitrine.ler_analises(self.caminho)], ["REQ-1", "REQ-2"])
        with open(self.caminho, encoding="utf-8") as f:
            self.assertIn("analises", json.load(f))

    def test_mesmo_id_substitui(self):
        self.adicionar(PEDIDO, "REQ-1", RESULTADO)
        self.adicionar(PEDIDO, "REQ-2")
        self.adicionar(PEDIDO, "REQ-1")                       # reprocessada: substitui e vai pro fim
        analises = vitrine.ler_analises(self.caminho)
        self.assertEqual([a["id"] for a in analises], ["REQ-2", "REQ-1"])
        self.assertEqual(analises[-1]["amplicon_bp"], 0)

    def test_remover(self):
        self.adicionar(PEDIDO, "REQ-1")
        self.assertTrue(vitrine.remover_analise("REQ-1", self.caminho))
        self.assertFalse(vitrine.remover_analise("REQ-1", self.caminho))
        self.assertEqual(vitrine.ler_analises(self.caminho), [])

    def test_arquivo_inexistente(self):
        self.assertEqual(vitrine.ler_analises(self.caminho), [])

    def test_nao_deixa_temporario(self):
        self.adicionar(PEDIDO, "REQ-1")
        self.assertEqual(os.listdir(self.pasta.name), ["vitrine.json"])

    def test_vitrine_publicada_e_valida(self):
        # O arquivo de verdade tem que continuar legível e sem IDs repetidos.
        analises = vitrine.ler_analises()
        ids = [a["id"] for a in analises]
        self.assertEqual(len(ids), len(set(ids)))
        for a in analises:
            self.assertEqual(set(a), {"id", "nome_par", "alvo", "banco", "forward", "reverse", "amplicon_bp", "data"})


if __name__ == "__main__":
    unittest.main()
