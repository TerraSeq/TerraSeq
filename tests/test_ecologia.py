"""
Testes da classificação ecológica (src/ecologia.py).

Rodar, na raiz do projeto (não precisa de BLAST, .env nem internet):

    python3 -m unittest discover tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ecologia import FUNCOES_ECOLOGICAS, NAO_CLASSIFICADO, classificar_ecologia  # noqa: E402


class TestClassificarEcologia(unittest.TestCase):

    def test_fungo(self):
        linhagem = ["Eukaryota", "Opisthokonta", "Fungi", "Dikarya", "Ascomycota", "Aspergillus niger"]
        self.assertEqual(classificar_ecologia(linhagem), ("Fungos", "Microrganismos", "Microrganismos"))

    def test_bacteria(self):
        linhagem = ["Bacteria", "Pseudomonadota", "Gammaproteobacteria", "Pseudomonas putida"]
        self.assertEqual(classificar_ecologia(linhagem)[0], "Bactérias")

    def test_enquitreideo_vence_minhoca(self):
        # Enchytraeidae também é Oligochaeta: a regra mais específica tem que vir antes.
        linhagem = ["Eukaryota", "Metazoa", "Annelida", "Clitellata", "Oligochaeta", "Enchytraeidae", "Enchytraeus albidus"]
        self.assertEqual(classificar_ecologia(linhagem), ("Enquitreídeos", "Mesofauna / Macrofauna", "Engenheiros do Ecossistema"))

    def test_minhoca(self):
        linhagem = ["Eukaryota", "Metazoa", "Annelida", "Clitellata", "Oligochaeta", "Lumbricidae", "Lumbricus terrestris"]
        self.assertEqual(classificar_ecologia(linhagem)[0], "Minhocas")

    def test_acaro_vence_aracnideo(self):
        # Ácaros também são Arachnida: Ácaros (decompositores) vêm antes de Aracnídeos (micropredadores).
        linhagem = ["Eukaryota", "Metazoa", "Arthropoda", "Arachnida", "Acari", "Acariformes", "Oribatida", "Oppia nitens"]
        self.assertEqual(classificar_ecologia(linhagem), ("Ácaros", "Mesofauna", "Decompositores da Serrapilheira"))

    def test_aracnideo_pelo_termo_arachnida(self):
        # Termo que faltava na cópia do main_issues.py antes da unificação.
        linhagem = ["Eukaryota", "Metazoa", "Arthropoda", "Arachnida", "Solifugae", "Galeodes sp."]
        self.assertEqual(classificar_ecologia(linhagem)[2], "Micropredadores")

    def test_protista_apusomonadida(self):
        # Também faltava no main_issues.py (era "Não Classificado" nas Issues).
        linhagem = ["Eukaryota", "Apusozoa", "Apusomonadida", "Apusomonadidae", "Thecamonas", "Thecamonas trahens ATCC 50062"]
        self.assertEqual(classificar_ecologia(linhagem)[0], "Protistas")

    def test_formiga_vence_inseto(self):
        linhagem = ["Eukaryota", "Metazoa", "Arthropoda", "Hexapoda", "Insecta", "Hymenoptera", "Formicidae", "Atta sexdens"]
        self.assertEqual(classificar_ecologia(linhagem)[0], "Formigas")

    def test_fora_do_escopo(self):
        linhagem = ["Eukaryota", "Metazoa", "Chordata", "Vertebrata", "Mammalia", "Mus musculus"]
        self.assertEqual(classificar_ecologia(linhagem)[2], "Fora do Escopo Principal")

    def test_maiusculas_nao_importam(self):
        self.assertEqual(classificar_ecologia(["EUKARYOTA", "FUNGI"])[0], "Fungos")

    def test_nao_classificado(self):
        self.assertEqual(classificar_ecologia(["Eukaryota", "Grupo inventado", "Especie x"]), NAO_CLASSIFICADO)
        self.assertEqual(classificar_ecologia([]), NAO_CLASSIFICADO)

    def test_funcoes_ecologicas(self):
        self.assertEqual(FUNCOES_ECOLOGICAS, sorted([
            "Decompositores da Serrapilheira", "Engenheiros do Ecossistema", "Fora do Escopo Principal",
            "Função Indefinida", "Micropredadores", "Microrganismos",
        ]))


if __name__ == "__main__":
    unittest.main()
