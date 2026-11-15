"""
Testes de bancos.py, resultados_blast.py e relatorio.py (as partes da
run_pipeline). Sem BLAST, banco nem internet.

Rodar, na raiz do projeto:

    python3 -m unittest discover tests
"""
import csv
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import bancos  # noqa: E402
import relatorio  # noqa: E402
import resultados_blast  # noqa: E402


class TestBancos(unittest.TestCase):

    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.dir = self.pasta.name
        # índices falsos: bacteria em 2 volumes (.00/.01), o resto num arquivo só
        for nome in ["bacteria.00.nsq", "bacteria.01.nsq", "bacteria.nal", "archaea.nsq",
                     "formicidae.nsq", "formicidae.nhr", "ascomycota.nsq", "nematoda.nsq"]:
            open(os.path.join(self.dir, nome), "w").close()
        contagem = {"formicidae": 213, "bacteria": 22000, "archaea": 800, "ascomycota": None, "nematoda": 250}
        self.patch = mock.patch.object(bancos.taxonomia_local, "contagem_organismos_grupo", side_effect=contagem.get)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.pasta.cleanup()

    def test_grupos_indexados(self):
        self.assertEqual(bancos.grupos_indexados(self.dir), ["archaea", "ascomycota", "bacteria", "formicidae", "nematoda"])
        self.assertEqual(bancos.grupos_indexados(self.dir + "_nao_existe"), [])

    def test_apelido(self):
        b = bancos.resolver("formigas", self.dir)
        self.assertEqual((b.grupos, b.caminho_blast, b.total_genomas), (["formicidae"], os.path.join(self.dir, "formicidae"), 213))

    def test_composto_na_ordem_certa(self):
        b = bancos.resolver("fungi", self.dir)
        self.assertEqual(b.grupos[:2], ["basidiomycota", "ascomycota"])
        self.assertEqual(b.caminho_blast.split(" ")[0], os.path.join(self.dir, "basidiomycota"))

    def test_eucariotos_sem_procariontes(self):
        self.assertEqual(bancos.resolver("eucariotos", self.dir).grupos, ["ascomycota", "formicidae", "nematoda"])
        self.assertEqual(bancos.resolver("refseqsoil", self.dir).grupos, ["archaea", "ascomycota", "bacteria", "formicidae", "nematoda"])

    def test_contagem_sem_manifesto_usa_valor_antigo(self):
        # ascomycota sem manifesto e sem valor antigo -> 0; nematoda tem manifesto
        self.assertEqual(bancos.genomas_do_grupo("ascomycota"), 0)
        self.assertEqual(bancos.resolver("procariotos", self.dir).total_genomas, 22800)

    def test_banco_desconhecido(self):
        self.assertIsNone(bancos.resolver("nao_existe", self.dir))
        self.assertNotIn("nao_existe", bancos.nomes())
        self.assertIn("cupins", bancos.nomes())


class TestResultadosBlast(unittest.TestCase):

    def gravar_csv(self, linhas):
        f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="")
        w = csv.writer(f)
        w.writerow(["Subject_ID", "Amplicon_size", "Start", "End", "Raw_hits_no_genoma", "Amplicon_sequence", "amplicon_tm"])
        w.writerows(linhas)
        f.close()
        self.addCleanup(os.remove, f.name)
        return f.name

    def test_le_hits(self):
        arq = self.gravar_csv([["gb|AAA01000001.1|", 600, 1, 600, 3, "ACGT", 80.1],
                               ["gb|AAA01000001.1|", 620, 5, 625, 3, "ACGTA", 80.2],
                               ["NC_0001.2", "x", 1, 2, 1, "GG", "N/A"]])
        hits = resultados_blast.ler_hits(arq)
        self.assertEqual(hits.total, 3)
        self.assertEqual(hits.media_amplicon, (600 + 620) / 3)       # tamanho inválido conta 0
        self.assertEqual(list(hits.por_sequencia), ["gb|AAA01000001.1|", "NC_0001.2"])
        amp = hits.por_sequencia["gb|AAA01000001.1|"][0]
        self.assertEqual((amp["acc"], amp["size"], amp["tm"], amp["raw_hits_genoma"], amp["seq"]), ("AAA01000001", "600", "80.1", "3", "ACGT"))

    def test_sem_arquivo(self):
        hits = resultados_blast.ler_hits("/nao/existe.csv")
        self.assertEqual((hits.por_sequencia, hits.total, hits.media_amplicon), ({}, 0, 0))

    def test_orcamentos_de_sequencia(self):
        arq = self.gravar_csv([[f"S{i}", 10, 1, 10, 1, "A" * 10, 70] for i in range(4)])
        with mock.patch.object(resultados_blast, "ORCAMENTO_MAX_CARACTERES_SEQ", 10), \
             mock.patch.object(resultados_blast, "ORCAMENTO_MAX_CARACTERES_SEQ_COMPLETA", 10):
            hits = resultados_blast.ler_hits(arq)
        amps = [hits.por_sequencia[f"S{i}"][0] for i in range(4)]
        self.assertEqual(amps[0]["seq"], "A" * 10)                                # cabe no result.json
        self.assertEqual(amps[1]["seq"], resultados_blast.AVISO_SEQ_NO_FASTA)       # só no FASTA
        self.assertEqual(amps[1]["_seq_completa"], "A" * 10)
        self.assertEqual(amps[2]["seq"], resultados_blast.AVISO_SEQ_SO_NO_SERVIDOR)  # nem no FASTA
        self.assertTrue(amps[2]["omitido"] and amps[1]["omitido"] and not amps[0]["omitido"])

        metadados = {"Especie a": {"amplicons": amps[:2]}, "Especie b": {"amplicons": amps[2:]}}
        self.assertEqual(resultados_blast.separar_sequencias_completas(metadados), {"Especie a": [None, "A" * 10]})
        self.assertNotIn("_seq_completa", amps[1])


class TestRelatorio(unittest.TestCase):

    def test_cobertura_e_avisos(self):
        self.assertEqual(relatorio.calcular_cobertura(155, 213), 155 / 213)
        self.assertEqual(relatorio.calcular_cobertura(5, 0), 0)
        self.assertEqual(relatorio.avisos_do_relatorio(0.9, 1), [])
        avisos = relatorio.avisos_do_relatorio(0.3, 3, "acervo antigo")
        self.assertEqual(len(avisos), 3)
        self.assertIn("Cobertura geral baixa", avisos[0])

    def test_organismos_nao_capturados(self):
        with tempfile.TemporaryDirectory() as raiz:
            os.makedirs(os.path.join(raiz, "docs", "dados"))
            acervo = {"gerado_em": "2026-11-01", "bancos": [
                {"id": "formicidae", "organismos": ["Atta sexdens", "Atta cephalotes", "Solenopsis invicta"]},
                {"id": "nematoda", "organismos": ["C. elegans"]}]}
            with open(os.path.join(raiz, "docs", "dados", "acervo_genomas.json"), "w") as f:
                json.dump(acervo, f)
            fora, aviso = relatorio.calcular_organismos_nao_capturados(raiz, ["formicidae"], ["Atta sexdens"])
            self.assertEqual(fora, ["Atta cephalotes", "Solenopsis invicta"])
            self.assertIn("2026-11-01", aviso)
            fora, aviso = relatorio.calcular_organismos_nao_capturados(raiz, ["tardigrada"], [])
            self.assertIsNone(fora)
        fora, aviso = relatorio.calcular_organismos_nao_capturados("/nao/existe", ["formicidae"], [])
        self.assertIsNone(fora)
        self.assertIn("não encontrado", aviso)


if __name__ == "__main__":
    unittest.main()
