"""
Testes da montagem das árvores do relatório (src/arvore_taxonomica.py).

A base de taxonomia local e o NCBI são substituídos por versões falsas: o
teste não precisa do taxdump, de manifesto nem de internet.

Rodar, na raiz do projeto:

    python3 -m unittest discover tests
"""
import contextlib
import io
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import arvore_taxonomica  # noqa: E402
from arvore_taxonomica import accession_do_id, construir_arvore_aninhada, descobrir_rank  # noqa: E402

LINHAGENS = {
    # accession: (taxid, linhagem como a base local devolve)
    "AAA001": ("1", ["cellular organisms", "Eukaryota", "Fungi", "Ascomycota", "Eurotiomycetes", "Eurotiales", "Aspergillaceae", "Aspergillus", "Aspergillus niger"]),
    "AAA002": ("2", ["cellular organisms", "Eukaryota", "Fungi", "Ascomycota", "Eurotiomycetes", "Eurotiales", "Aspergillaceae", "Aspergillus", "Aspergillus flavus"]),
    "BBB001": ("3", ["cellular organisms", "Bacteria", "Pseudomonadota", "Gammaproteobacteria", "Pseudomonadales", "Pseudomonadaceae", "Pseudomonas", "Pseudomonas putida"]),
}


class TaxonomiaFalsa:
    def taxid_por_accession(self, acc):
        return LINHAGENS.get(acc, (None,))[0]

    def linhagem_por_taxid(self, taxid):
        return next(list(lin) for t, lin in LINHAGENS.values() if t == taxid)

    def descricao_e_tamanho_por_accession(self, acc):
        return f"descrição de {acc}", 5000


class EntrezForaDoAr:
    def efetch(self, **kwargs):
        raise RuntimeError("NCBI fora do ar")


def montar(ids, hits):
    total = sum(len(v) for v in hits.values())
    with mock.patch.object(arvore_taxonomica, "taxonomia_local", TaxonomiaFalsa()), \
         mock.patch.object(arvore_taxonomica, "Entrez", EntrezForaDoAr()), \
         mock.patch.object(arvore_taxonomica, "time", types.SimpleNamespace(sleep=lambda s: None)), \
         contextlib.redirect_stdout(io.StringIO()):
        return construir_arvore_aninhada(ids, total, hits)


def filho(no, nome):
    return next(c for c in no["children"] if c["name"] == nome)


class TestAccessionDoId(unittest.TestCase):

    def test_formatos(self):
        self.assertEqual(accession_do_id("gb|JBAMJC010000001.1|"), "JBAMJC010000001")
        self.assertEqual(accession_do_id("ref|NC_000913.3|"), "NC_000913")
        self.assertEqual(accession_do_id("NC_000913.3"), "NC_000913")
        self.assertEqual(accession_do_id("OZ209258"), "OZ209258")


class TestDescobrirRank(unittest.TestCase):

    def test_ranks(self):
        self.assertEqual(descobrir_rank("Bacteria", 0, 8), "domain")
        self.assertEqual(descobrir_rank("Fungi", 1, 8), "kingdom")
        self.assertEqual(descobrir_rank("Ascomycota", 2, 8), "phylum")
        self.assertEqual(descobrir_rank("Eurotiomycetes", 3, 8), "class")
        self.assertEqual(descobrir_rank("Eurotiales", 4, 8), "order")
        self.assertEqual(descobrir_rank("Aspergillaceae", 5, 8), "family")
        self.assertEqual(descobrir_rank("Aspergillus", 6, 8), "genus")
        self.assertEqual(descobrir_rank("Aspergillus niger", 7, 8), "species")


class TestConstruirArvore(unittest.TestCase):

    def setUp(self):
        self.hits = {
            "gb|AAA001.1|": ["h1", "h2"],      # 2 hits na mesma sequência
            "AAA002.1": ["h3"],
            "BBB001": ["h4"],
            "ZZZ999.1": ["h5"],                # sem taxonomia local e NCBI fora do ar
        }
        self.arvore, self.meta, self.funcional = montar(list(self.hits), self.hits)

    def test_raiz_e_dominios(self):
        self.assertEqual(self.arvore["name"], "Root")
        self.assertEqual(self.arvore["matches"], 5)
        self.assertEqual(sorted(c["name"] for c in self.arvore["children"]), ["Bacteria", "Eukaryota", "Unclassified"])

    def test_cellular_organisms_removido(self):
        self.assertNotIn("cellular organisms", [c["name"] for c in self.arvore["children"]])

    def test_contagem_por_hit(self):
        # Cada hit conta (o gene multi-cópia com 2 hits pesa 2), e cobertura = hits / total.
        eukaryota = filho(self.arvore, "Eukaryota")
        self.assertEqual(eukaryota["matches"], 3)
        self.assertEqual(eukaryota["coverage"], 0.6)
        aspergillus = filho(filho(filho(filho(filho(filho(eukaryota, "Fungi"), "Ascomycota"), "Eurotiomycetes"), "Eurotiales"), "Aspergillaceae"), "Aspergillus")
        self.assertEqual(filho(aspergillus, "Aspergillus niger")["matches"], 2)
        self.assertEqual(filho(aspergillus, "Aspergillus niger")["rank"], "species")

    def test_nao_classificado_vira_ramo_clicavel(self):
        unclassified = filho(self.arvore, "Unclassified")
        self.assertEqual([c["name"] for c in unclassified["children"]], ["ZZZ999"])
        self.assertIn("não classificado", self.meta["ZZZ999"]["info"]["desc"].lower())
        especies = self.funcional["Função Indefinida"]["Não Classificado"]["especies"]
        self.assertEqual([e["especie"] for e in especies], ["ZZZ999"])

    def test_metadados(self):
        self.assertEqual(self.meta["Aspergillus niger"]["info"], {"acc": "AAA001", "desc": "descrição de AAA001", "length": 5000})
        self.assertEqual(self.meta["Aspergillus niger"]["amplicons"], ["h1", "h2"])

    def test_classificacao_funcional(self):
        fungos = self.funcional["Microrganismos"]["Fungos"]
        self.assertEqual(fungos["tamanho"], "Microrganismos")
        self.assertEqual([(e["especie"], e["matches"]) for e in fungos["especies"]],
                         [("Aspergillus niger", 2), ("Aspergillus flavus", 1)])
        self.assertIn("Bactérias", self.funcional["Microrganismos"])
        # Todas as funções existem, mesmo vazias.
        self.assertEqual(self.funcional["Engenheiros do Ecossistema"], {})

    def test_sem_hits(self):
        arvore, meta, _ = montar([], {})
        self.assertEqual(arvore["children"], [])
        self.assertEqual(arvore["coverage"], 0.0)      # sem hits, nada a dividir
        self.assertEqual(meta, {})


if __name__ == "__main__":
    unittest.main()
