#!/usr/bin/env python3
"""
Teste: um banco so com a regiao do rRNA da MESMA lista de sequencias de um
banco atual (ex: formicidae) da o mesmo resultado, mais rapido?

Dois passos, no servidor (precisa de blastdbcmd/makeblastdb do BLAST+ e do
barrnap -- `conda install -c bioconda barrnap` ou `apt install barrnap`):

  1) criar o banco recortado a partir do banco existente
       python3 scripts_auxiliares/testar_banco_rrna.py criar \\
           --banco data/blast_dbs/formicidae --saida data/blast_dbs_teste/formicidae_rrna

     Dumpa as sequencias do banco, roda o barrnap (eucariotos), e para cada
     sequencia com rRNA guarda so o trecho que vai do primeiro ao ultimo gene
     de rRNA (agrupados a ate --gap pb um do outro), com --folga pb de cada
     lado. O cabecalho original e mantido, entao _genome_key e a taxonomia
     continuam funcionando. Nao mexe no banco original.

  2) comparar o mesmo par de primers nos dois bancos
       python3 scripts_auxiliares/testar_banco_rrna.py comparar \\
           --original data/blast_dbs/formicidae \\
           --recortado data/blast_dbs_teste/formicidae_rrna \\
           --fwd CCAGCASCYGCGGTAATTCC --rev RCCACAAGCYARTTATCC \\
           --min-amplicon 2000 --max-amplicon 8000

     Mostra, para cada banco: tempo do BLAST, hits, genomas (contigs do
     mesmo genoma contam 1) e os genomas que so um dos bancos achou.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, RAIZ)


def ler_fasta(caminho):
    cab, seq = None, []
    with open(caminho) as f:
        for linha in f:
            linha = linha.rstrip("\n")
            if linha.startswith(">"):
                if cab is not None:
                    yield cab, "".join(seq)
                cab, seq = linha[1:], []
            else:
                seq.append(linha)
    if cab is not None:
        yield cab, "".join(seq)


def trechos_de_rrna(gff, gap):
    """Le o GFF do barrnap e devolve {contig: (inicio, fim)} (1-based, inclusivo)
    do maior conjunto de genes de rRNA vizinhos (a ate `gap` pb um do outro)."""
    por_contig = {}
    with open(gff) as f:
        for linha in f:
            if linha.startswith("#") or not linha.strip():
                continue
            c = linha.rstrip("\n").split("\t")
            if len(c) < 5:
                continue
            por_contig.setdefault(c[0], []).append((int(c[3]), int(c[4])))
    resultado = {}
    for contig, genes in por_contig.items():
        genes.sort()
        grupos, atual = [], [genes[0]]
        for g in genes[1:]:
            if g[0] - atual[-1][1] <= gap:
                atual.append(g)
            else:
                grupos.append(atual)
                atual = [g]
        grupos.append(atual)
        melhor = max(grupos, key=lambda gr: (len(gr), gr[-1][1] - gr[0][0]))
        resultado[contig] = (min(g[0] for g in melhor), max(g[1] for g in melhor))
    return resultado


def criar(args):
    for exe in ("blastdbcmd", "makeblastdb"):
        if not shutil.which(exe) and not args.gff:
            sys.exit(f"❌ {exe} nao encontrado no PATH.")
    os.makedirs(os.path.dirname(os.path.abspath(args.saida)) or ".", exist_ok=True)
    trabalho = tempfile.mkdtemp(prefix="rrna_")
    fasta = os.path.join(trabalho, "todas.fa")
    gff = args.gff or os.path.join(trabalho, "rrna.gff")

    if not args.gff:
        print(f"📤 Extraindo sequencias de {args.banco} ...")
        subprocess.run(f'blastdbcmd -db "{args.banco}" -entry all -outfmt %f -out "{fasta}"',
                       shell=True, check=True)
        if os.path.getsize(fasta) == 0:
            sys.exit(f"❌ blastdbcmd nao devolveu sequencias de {args.banco}.")
        if not shutil.which("barrnap"):
            sys.exit("❌ barrnap nao encontrado (conda install -c bioconda barrnap).")
        print("🧬 Rodando barrnap (eucariotos) ...")
        with open(gff, "w") as out:
            subprocess.run(["barrnap", "--kingdom", "euk", "--threads", str(args.threads), "--quiet", fasta],
                           check=True, stdout=out)
    else:
        fasta = args.fasta
        if not fasta:
            sys.exit("❌ com --gff informe tambem --fasta.")

    trechos = trechos_de_rrna(gff, args.gap)
    total = com_rrna = bases_in = bases_out = 0
    saida_fa = os.path.join(trabalho, "rrna.fa")
    with open(saida_fa, "w") as out:
        for cab, seq in ler_fasta(fasta):
            total += 1
            bases_in += len(seq)
            contig = cab.split()[0]
            if contig not in trechos:
                continue
            ini, fim = trechos[contig]
            ini = max(1, ini - args.folga)
            fim = min(len(seq), fim + args.folga)
            pedaco = seq[ini - 1:fim]
            com_rrna += 1
            bases_out += len(pedaco)
            out.write(f">{cab}\n{pedaco}\n")

    print(f"\n   sequencias no banco original : {total:,}  ({bases_in/1e6:,.1f} Mb)")
    print(f"   sequencias com rRNA          : {com_rrna:,}  ({bases_out/1e6:,.2f} Mb)")
    if bases_in:
        print(f"   tamanho do banco recortado   : {100*bases_out/bases_in:.3f}% do original")
    if com_rrna == 0:
        sys.exit("❌ Nenhum rRNA encontrado; nada a indexar.")
    subprocess.run(f'makeblastdb -in "{saida_fa}" -dbtype nucl -parse_seqids -out "{args.saida}"',
                   shell=True, check=True)
    print(f"✅ Banco recortado em {args.saida}")
    shutil.rmtree(trabalho, ignore_errors=True)


def rodar_um(banco, fwd, rev, args, pasta):
    import run_parse_blastn as r
    fasta = os.path.join(pasta, "primer.fasta")
    with open(fasta, "w") as f:
        f.write(f">P|Target|fwd\n{fwd}\n>P|Target|rev\n{rev}\n")
    saida = os.path.join(pasta, "blast.out")
    log = os.path.join(pasta, "log.txt")
    t0 = time.time()
    r._call_blastn(fasta, f'"{banco}"', args.threads, args.evalue, 30000, args.cobertura, log, saida)
    tempo = time.time() - t0
    d = r._blast_to_dict(saida)
    passando, _ = r._evaluate_hit_loc(d, {"P|fwd": fwd, "P|rev": rev}, tm_thresh=args.tm,
                                      size_max=args.max_amplicon, size_min=args.min_amplicon,
                                      max_3prime_mm=args.mismatches_3)
    linhas = passando.strip().split("\n")[1:]
    genomas = {r._genome_key(l.split(",")[3]) for l in linhas if l}
    hits = sum(len(v) for ens in d.values() for dire in ens.values() for v in dire.values())
    return tempo, hits, len(linhas), genomas


def comparar(args):
    pasta = tempfile.mkdtemp(prefix="cmp_")
    res = {}
    for nome, banco in (("original", args.original), ("recortado", args.recortado)):
        print(f"\n▶ {nome}: {banco}")
        sub = os.path.join(pasta, nome)
        os.makedirs(sub)
        res[nome] = rodar_um(banco, args.fwd, args.rev, args, sub)
    print(f"\n{'':12}{'tempo':>10}{'hits brutos':>14}{'pares':>8}{'genomas':>9}")
    for nome, (t, h, p, g) in res.items():
        print(f"{nome:12}{t:>9.1f}s{h:>14,}{p:>8,}{len(g):>9,}")
    so_orig = res["original"][3] - res["recortado"][3]
    so_rec = res["recortado"][3] - res["original"][3]
    print(f"\nGenomas so no original  : {len(so_orig)}")
    print(f"Genomas so no recortado : {len(so_rec)}")
    for g in sorted(so_orig)[:15]:
        print("   só original :", g)
    for g in sorted(so_rec)[:15]:
        print("   só recortado:", g)
    shutil.rmtree(pasta, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("criar")
    c.add_argument("--banco", help="banco BLAST de origem (prefixo, ex: data/blast_dbs/formicidae)")
    c.add_argument("--saida", required=True)
    c.add_argument("--threads", type=int, default=8)
    c.add_argument("--gap", type=int, default=20000, help="distancia max. entre genes de rRNA do mesmo trecho")
    c.add_argument("--folga", type=int, default=500, help="pb extras de cada lado do trecho")
    c.add_argument("--gff", help="(teste) usa este GFF em vez de rodar o barrnap")
    c.add_argument("--fasta", help="(teste) FASTA correspondente ao --gff")
    c.set_defaults(f=criar)
    m = sub.add_parser("comparar")
    m.add_argument("--original", required=True)
    m.add_argument("--recortado", required=True)
    m.add_argument("--fwd", required=True)
    m.add_argument("--rev", required=True)
    m.add_argument("--min-amplicon", type=int, default=2000)
    m.add_argument("--max-amplicon", type=int, default=8000)
    m.add_argument("--mismatches-3", type=int, default=3)
    m.add_argument("--cobertura", type=float, default=70)
    m.add_argument("--evalue", type=float, default=10.0)
    m.add_argument("--tm", type=float, default=0.0)
    m.add_argument("--threads", type=int, default=1, help="1 e obrigatorio com bancos split")
    m.set_defaults(f=comparar)
    args = ap.parse_args()
    if args.cmd == "criar" and not args.gff and not args.banco:
        ap.error("informe --banco")
    args.f(args)


if __name__ == "__main__":
    main()
