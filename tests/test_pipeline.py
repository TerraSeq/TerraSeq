"""
Teste de ponta a ponta de pipeline.run_pipeline com BLAST e taxonomia falsos
(roda em ~1 segundo, sem BLAST, banco, taxdump, .env nem internet).

O relatório de teste é gravado em docs/reports/TESTE-UNIT-.../ (ignorado pelo
Git) e apagado no fim.

Para o teste com o BLAST de verdade, no servidor:
    python3 scripts_auxiliares/testar_pipeline.py issue

Rodar, na raiz do projeto:
    python3 -m unittest discover tests
"""
import contextlib
import csv
import io
import json
import os
import shutil
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import arvore_taxonomica  # noqa: E402
import pipeline  # noqa: E402

PEDIDO = {
    "Nome completo": "Teste", "Email": "teste@example.com", "Nome do Par de Primers": "TESTE_PAR",
    "Primer forward": "ccagcascygcggtaattcc", "Primer reverse": "GAGAGTCATAGTTACBYC",
    "Região alvo": "18S", "Banco de Dados": "formigas", "Tipo de organismo": "Eukaryota",
    "Máximo de Mismatches na extremidade 3": "3", "Tamanho do amplicon: MIN": "2000",
    "Tamanho do amplicon: MAX": "8000", "Temperatura de Melting mínima (Tm)": "0",
    "E-value máximo": "10", "Cobertura mínima": "70",
}

# (Subject_ID, tamanho do amplicon): 2 hits na mesma sequência, 3 espécies de formiga e 1 fungo
HITS = [("gb|JBAA01000001.1|", 6100), ("gb|JBAA01000001.1|", 6120), ("ref|NW_0001.1|", 6150),
        ("JBBB01000005.1", 5980), ("JBCC01000001.1", 6300)]
LINHAGENS = {
    "JBAA01000001": ("1", ["Eukaryota", "Metazoa", "Arthropoda", "Insecta", "Hymenoptera", "Formicidae", "Atta", "Atta sexdens"]),
    "NW_0001": ("2", ["cellular organisms", "Eukaryota", "Metazoa", "Arthropoda", "Insecta", "Hymenoptera", "Formicidae", "Solenopsis", "Solenopsis invicta"]),
    "JBBB01000005": ("3", ["Eukaryota", "Metazoa", "Arthropoda", "Insecta", "Hymenoptera", "Formicidae", "Atta", "Atta cephalotes"]),
    "JBCC01000001": ("4", ["Eukaryota", "Fungi", "Ascomycota", "Sordariomycetes", "Hypocreales", "Escovopsis", "Escovopsis weberi"]),
}


class TaxonomiaFalsa:
    def taxid_por_accession(self, acc):
        return LINHAGENS.get(acc, (None,))[0]

    def linhagem_por_taxid(self, taxid):
        return next(list(lin) for t, lin in LINHAGENS.values() if t == taxid)

    def descricao_e_tamanho_por_accession(self, acc):
        return f"descrição de {acc}", 4321

    def contar_genomas_distintos(self, ids):
        return len({arvore_taxonomica.accession_do_id(i) for i in ids})

    def contagem_organismos_grupo(self, grupo):
        return {"formicidae": 213}.get(grupo)


def blast_falso(cmd, **kwargs):
    """Faz o papel do primer_blast_local.py: grava o CSV de pares válidos."""
    saida = cmd[cmd.index("-o") + 1]
    with open(saida + "__results.pass.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Assay_name_and_target", "Forward_primer_seq", "Reverse_primer_seq", "Subject_ID", "Tm_forward",
                    "Tm_reverse", "Amplicon_size", "Start", "End", "Raw_hits_no_genoma", "Amplicon_sequence", "amplicon_tm"])
        for sid, tamanho in HITS:
            w.writerow(["Ensaio|Target", "F", "R", sid, "60.1", "59.8", tamanho, 100, 100 + tamanho, 2, "ACGT" * 10, "78.5"])
    return mock.Mock(returncode=0, stdout="", stderr="")


class TestRunPipeline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.req_id = f"TESTE-UNIT-{os.getpid()}-{int(time.time())}"
        cls.chamadas = []

        def registrar(cmd, **kwargs):
            cls.chamadas.append(cmd)
            return blast_falso(cmd, **kwargs)

        tax = TaxonomiaFalsa()
        with mock.patch.object(pipeline.subprocess, "run", side_effect=registrar), \
             mock.patch.object(pipeline, "taxonomia_local", tax), \
             mock.patch.object(arvore_taxonomica, "taxonomia_local", tax), \
             contextlib.redirect_stdout(io.StringIO()) as log:
            cls.caminho, cls.resultado = pipeline.run_pipeline(dict(PEDIDO), cls.req_id, origem="TESTE")
        cls.log = log.getvalue()
        cls.pasta = os.path.join(os.path.dirname(__file__), "..", cls.caminho)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.pasta, ignore_errors=True)

    def test_arquivos_do_relatorio(self):
        self.assertEqual(self.caminho, f"docs/reports/{self.req_id}")
        for nome in ("result.json", "index.html", "primer.fasta"):
            self.assertTrue(os.path.exists(os.path.join(self.pasta, nome)), nome)
        with open(os.path.join(self.pasta, "result.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["request_id"], self.req_id)

    def test_comando_do_blast(self):
        cmd = self.chamadas[0]
        self.assertIn("primer_blast_local.py", cmd)
        self.assertEqual(cmd[cmd.index("--min_size") + 1], "2000")
        self.assertEqual(cmd[cmd.index("--max_3prime_mismatches") + 1], "3")
        self.assertEqual(cmd[cmd.index("-t") + 1], "1")

    def test_primers_e_metadados(self):
        r = self.resultado
        self.assertEqual(r["primers"]["forward"], "CCAGCASCYGCGGTAATTCC")     # vira maiúsculo
        self.assertEqual(r["primers"]["pair_name"], "TESTE_PAR")
        self.assertEqual(r["metadata"]["database"], "formigas")

    def test_resumo(self):
        s = self.resultado["summary"]
        self.assertEqual(s["total_matches"], 5)
        self.assertEqual(s["mean_amplicon_size"], round(sum(t for _, t in HITS) / 5, 1))
        self.assertEqual(s["total_sequences_checked"], 213)
        self.assertEqual(s["unique_organisms"], 4)
        self.assertAlmostEqual(s["estimated_coverage"], 4 / 213, places=4)

    def test_arvores(self):
        arvore = self.resultado["taxonomy_tree"]
        eukaryota = next(c for c in arvore["children"] if c["name"] == "Eukaryota")
        self.assertEqual(eukaryota["matches"], 5)
        funcional = self.resultado["functional_tree"]
        self.assertIn("Formigas", funcional["Engenheiros do Ecossistema"])
        self.assertIn("Fungos", funcional["Microrganismos"])

    def test_metadados_das_especies(self):
        atta = self.resultado["leaf_metadata"]["Atta sexdens"]
        self.assertEqual(len(atta["amplicons"]), 2)
        self.assertEqual(atta["amplicons"][0]["raw_hits_genoma"], "2")

    def test_log_mostra_a_origem(self):
        self.assertIn("RAIO-X DA TESTE", self.log)
        self.assertIn("no banco formigas", self.log)


if __name__ == "__main__":
    unittest.main()
