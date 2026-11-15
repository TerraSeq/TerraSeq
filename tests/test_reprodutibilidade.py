"""
O mesmo pedido tem que dar o mesmo resultado em qualquer execução.

O Python sorteia o "hash" de textos a cada execução (PYTHONHASHSEED), e com
isso a ordem de qualquer set de textos. Se a escolha do par de primers de um
genoma depender dessa ordem, o amplicon, o contig e a Tm mudam de uma rodada
para outra (aconteceu: amplicon médio 6.169 / 6.170 / 6.181 bp no mesmo teste).

Cada caso roda em processos separados com sementes de hash diferentes.

Rodar, na raiz do projeto:

    python3 -m unittest discover tests
"""
import json
import os
import subprocess
import sys
import unittest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Roda _evaluate_hit_loc com um _check_primer_quals falso (todo par passa; o
# tamanho do amplicon depende do contig) e imprime o CSV de saída.
SCRIPT_PAREAMENTO = r"""
import json, sys
sys.path.insert(0, %(raiz)r)
import run_parse_blastn as r

def check_falso(x, y, fwd_seq, rev_seq, **kw):
    tamanho = 1000 + int(x["sseqid"].split(".")[0][-3:])
    return True, 60.0, 61.0, tamanho, 0, 0, 1, tamanho

r._check_primer_quals = check_falso
hit = lambda s: {"sseqid": s, "sstart": "1", "send": "20", "sstrand": "plus", "evalue": "0.01"}
# Genoma WGS "JBAMJC01" com o gene em 8 contigs (multi-cópia) + 2 genomas de contig único.
contigs = [f"JBAMJC01000{n:04d}.1" for n in (7, 3, 12, 1, 9, 5, 11, 2)] + ["NC_000913.3", "NZ_CP012345.1"]
fwd = {c: [hit(c)] for c in contigs}
rev = {c: [hit(c)] for c in reversed(contigs)}
passing, _ = r._evaluate_hit_loc({"Primer": {"fwd": fwd, "rev": rev}}, {"Primer|fwd": "ACGT", "Primer|rev": "TGCA"})
print(json.dumps(passing))
"""

SEMENTES = ["0", "1", "2", "3", "42", "12345"]


def rodar(script, semente):
    env = dict(os.environ, PYTHONHASHSEED=semente)
    saida = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, cwd=RAIZ)
    if saida.returncode != 0:
        raise AssertionError(saida.stderr)
    return json.loads(saida.stdout.strip().splitlines()[-1])


class TestReprodutibilidade(unittest.TestCase):

    def test_pareamento_igual_em_toda_execucao(self):
        script = SCRIPT_PAREAMENTO % {"raiz": RAIZ}
        resultados = {semente: rodar(script, semente) for semente in SEMENTES}
        self.assertEqual(len(set(resultados.values())), 1,
                         "o pareamento mudou conforme a semente de hash:\n" + "\n".join(f"{s}: {v!r}" for s, v in resultados.items()))

    def test_escolhe_o_primeiro_contig_do_blast(self):
        # Do genoma multi-cópia fica o primeiro contig na ordem do BLAST (o 0007),
        # e cada genoma aparece uma vez só.
        linhas = rodar(SCRIPT_PAREAMENTO % {"raiz": RAIZ}, "0").strip().split("\n")[1:]
        sujeitos = [linha.split(",")[3] for linha in linhas]
        self.assertEqual(sujeitos, ["JBAMJC010000007.1", "NC_000913.3", "NZ_CP012345.1"])
        self.assertEqual(linhas[0].split(",")[6], "1007")


if __name__ == "__main__":
    unittest.main()
