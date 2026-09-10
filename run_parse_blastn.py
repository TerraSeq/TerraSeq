#!/usr/bin/env python
from Bio.SeqUtils import MeltingTemp as mt
from Bio.Seq import Seq
from Bio.Data.IUPACData import ambiguous_dna_values as _IUPAC_AMBIGUOUS
from reformat import _decode_fasta_header
import numpy as np
import subprocess, os, re

def _other_dir(dir):
    if dir == "fwd":
        return "rev"
    else:
        return "fwd"

def _iupac_match(primer_base, genome_base):
    """
    Compara uma base do primer (que pode ser um codigo de degenerescencia
    IUPAC, ex: R = A ou G) contra uma base real do genoma. Retorna True se
    a base do genoma eh uma das bases aceitas pelo codigo do primer.
    Ex: _iupac_match('R', 'A') e _iupac_match('R', 'G') -> True
        _iupac_match('R', 'C') -> False
    """
    aceitas = _IUPAC_AMBIGUOUS.get(primer_base.upper())
    if aceitas is None:
        return primer_base.upper() == genome_base.upper()
    return genome_base.upper() in aceitas

def _count_matches(seq1, seq2, shift = 0):
    # seq1 = primer (pode ter bases degeneradas IUPAC), seq2 = sequencia do genoma
    count = 0
    for i in range(min([len(seq1), len(seq2)])):
        if i+shift < len(seq1) and _iupac_match(seq1[i+shift], seq2[i]):
            count += 1
    return count


def _find_3prime_mms(pseq, aseq): # find 3' end mismatches between primer and aligned sequence
    match_ct_arr = np.zeros(len(pseq))
    for shift in range(len(pseq)):
        match_ct_arr[shift] = _count_matches(pseq, aseq, shift = shift)
    best_shift = np.argmax(match_ct_arr)
    return len(pseq)+best_shift - len(aseq)

def _count_3prime_mms_in_last_5(pseq, aseq):
    """Conta mismatches nos últimos 5 bp da extremidade 3', respeitando bases
    degeneradas IUPAC do primer (pseq) contra a sequência real do genoma (aseq)."""
    last_5_p = pseq[-5:] if len(pseq) >= 5 else pseq
    last_5_a = aseq[-5:] if len(aseq) >= 5 else aseq
    return sum(1 for p, a in zip(last_5_p, last_5_a) if not _iupac_match(p, a))

def _resolve_degenerate_bases(primer_seq, aligned_seq):
    """
    Não existe uma única Tm termodinâmica para uma posição degenerada --
    fisicamente, um primer com base degenerada é uma MISTURA de moléculas
    concretas (ex: 'S' é, na prática, um pool de moléculas com G e moléculas
    com C nessa posição). Para calcular a Tm da molécula específica dessa
    mistura que de fato anelou nesse alvo, substituímos cada base degenerada
    do primer pela base real do genoma, sempre que ela for uma correspondência
    IUPAC válida (ex: primer 'S' + genoma 'G' -> 'G'). Quando a base do genoma
    NÃO é uma correspondência válida (mismatch real), a base do primer é
    mantida, para que o Tm_NN calcule corretamente a penalidade de mismatch.
    """
    resolvido = [
        a.upper() if _iupac_match(p, a) else p.upper()
        for p, a in zip(primer_seq, aligned_seq)
    ]
    # Sobra do primer sem par no alinhamento (não deve ocorrer sem gaps, mas
    # evita perder bases caso os dois lados tenham tamanhos diferentes).
    resolvido.append(primer_seq[len(aligned_seq):].upper())
    return "".join(resolvido)

def _check_primer_quals(hit1, hit2, fwd_seq, rev_seq, tm_thresh = 45., size_max=9999, size_min=20, max_3prime_mm=0, Na=50, K=0, Tris=0, Mg=0, dNTPs=0, saltcorr=5):
    if hit1["sseqid"] == hit2["sseqid"] and hit1["sstrand"] != hit2["sstrand"]: # Check opposite strand annealing
        end_diff = int(hit2["sstart"]) - int(hit1["sstart"]) # amplicon size
        if (hit1["sstrand"] == "plus" and end_diff > 0) or (hit1["sstrand"] == "minus" and end_diff < 0): # primers are convergent
            # c_seq deve ser o COMPLEMENTO simples de sseq (pareado base a base,
            # na mesma ordem de leitura de qseq), conforme a própria documentação
            # do Bio.SeqUtils.MeltingTemp.Tm_NN:
            #   Primer (seq):      5' ATGC...
            #   Template (c_seq):  3' TACG...
            # Usar reverse_complement() (como antes) inverte a ordem da sequência
            # e quebra o pareamento posição-a-posição que o Tm_NN espera --
            # chegando a lançar ValueError mesmo em matches perfeitos e sem
            # nenhuma base degenerada.
            #
            # Além disso, o Tm_NN não sabe calcular termodinâmica pra um código
            # IUPAC literal (ex: 'S'), porque não existe um único valor de Tm
            # pra uma posição degenerada -- por isso resolvemos cada base
            # degenerada do primer pra base real do genoma antes de calcular.
            qseq_fwd_resolvido = _resolve_degenerate_bases(hit1["qseq"], hit1["sseq"])
            try:
                if qseq_fwd_resolvido == hit1["sseq"]:
                    tm_fwd = mt.Tm_NN(qseq_fwd_resolvido, nn_table = mt.DNA_NN4, Na=Na, K=K, Tris=Tris, Mg=Mg, dNTPs=dNTPs, saltcorr=saltcorr)
                else:
                    tm_fwd = mt.Tm_NN(qseq_fwd_resolvido, c_seq = Seq(hit1["sseq"]).complement(), nn_table = mt.DNA_NN4, Na=Na, K=K, Tris=Tris, Mg=Mg, dNTPs=dNTPs, saltcorr=saltcorr)
            except ValueError:
                tm_fwd = 0
            qseq_rev_resolvido = _resolve_degenerate_bases(hit2["qseq"], hit2["sseq"])
            try:
                if qseq_rev_resolvido == hit2["sseq"]:
                    tm_rev = mt.Tm_NN(qseq_rev_resolvido, nn_table = mt.DNA_NN4, Na=Na, K=K, Tris=Tris, Mg=Mg, dNTPs=dNTPs, saltcorr=saltcorr)
                else:
                    tm_rev = mt.Tm_NN(qseq_rev_resolvido, c_seq = Seq(hit2["sseq"]).complement(), nn_table = mt.DNA_NN4, Na=Na, K=K, Tris=Tris, Mg=Mg, dNTPs=dNTPs, saltcorr=saltcorr)
            except ValueError:
                tm_rev = 0
            threeprime_end_mm_fwd = _find_3prime_mms(fwd_seq, hit1["sseq"])
            threeprime_end_mm_rev = _find_3prime_mms(rev_seq, hit2["sseq"])
            mm_3prime_fwd = _count_3prime_mms_in_last_5(fwd_seq, hit1["sseq"])
            mm_3prime_rev = _count_3prime_mms_in_last_5(rev_seq, hit2["sseq"])

            if tm_fwd >= tm_thresh and tm_rev >= tm_thresh and size_min <= abs(end_diff) <= size_max and mm_3prime_fwd <= max_3prime_mm and mm_3prime_rev <= max_3prime_mm:
                return True, tm_fwd, tm_rev, abs(end_diff), threeprime_end_mm_fwd, threeprime_end_mm_rev, int(hit1["sstart"]), int(hit2["sstart"])
            else:
                return False, tm_fwd, tm_rev, abs(end_diff), threeprime_end_mm_fwd, threeprime_end_mm_rev, int(hit1["sstart"]), int(hit2["sstart"])
        else:
            return False, 0., 0. , 0, 0, 0, 0, 0
    else:
        return False, 0., 0. , 0, 0, 0, 0, 0

def _call_makeblastdb(fasta, log_file):
    with open(log_file, "a") as log:
        db_basename = os.path.splitext(fasta)[0]
        subprocess.run(F" makeblastdb -in {fasta} -dbtype nucl -out {db_basename}__BLAST", check=True, shell=True, stderr=log)
    return F"{db_basename}__BLAST"

# Tamanho de banco de dados FIXO usado so para o calculo estatistico do
# e-value (opcao -dbsize do blastn). Sem isso, o blastn usa o tamanho real
# do(s) banco(s) combinados no "-db" para calcular a significancia -- e como
# os bancos de solo sao montados concatenando um numero variavel de grupos
# taxonomicos (de 1 ate 18+ bancos, alguns com genomas legitimamente enormes,
# como carrapatos e centopeias), o mesmo primer/match pode "passar" no e-value
# rodando contra um banco pequeno e "falhar" rodando contra o combinado
# grande -- nao porque o alinhamento mudou, mas porque a estatistica de
# significancia depende do tamanho do banco (E ~ tamanho_do_banco). Fixar um
# valor de referencia deixa o resultado do e-value consistente e prossivel,
# independente de quantos/quais bancos forem combinados numa busca.
# Convencao comum em pipelines de checagem de primers: usar a escala de UM
# genoma tipico (1 Gb) como referencia.
DBSIZE_REFERENCIA = 1_000_000_000

def _call_blastn(query, db, nt, ev, max_target_seqs, qcov_hsp_perc, log_file, out_file):
    # -task blastn-short: sem isso, o blastn usa "megablast" por padrao (task
    # feito pra sequencias LONGAS e quase identicas, ex: genoma x genoma), que
    # tem sensibilidade muito baixa pra sequencias curtas com mismatches --
    # como primers (~20 pb), especialmente contra bancos de dados grandes.
    # Definir so "-word_size 7" nao resolve, porque o algoritmo de
    # busca/extensao usado continua sendo o do megablast. A NCBI recomenda
    # blastn-short para qualquer query abaixo de 50 pb.
    cmd = F"blastn -task blastn-short -query {query} -db {db} -num_threads {nt} -word_size 7 -evalue {ev} -dbsize {DBSIZE_REFERENCIA} -outfmt \"6 qseqid sseqid qstart qend sstart send evalue pident qcovs qseq sseq sstrand\" -max_target_seqs {max_target_seqs}"

    if qcov_hsp_perc > 0:
        cmd += F" -qcov_hsp_perc {qcov_hsp_perc}"

    cmd += F" > {out_file}"
    
    with open(log_file, "a") as log:
        subprocess.run(cmd, check=True, shell=True, stderr=log)
        print(cmd)


def _blast_to_dict(file):
    '''
    Coverts the output BLASTN with FMT=6 to a dictionary of hits by query key.
    Agrupa FWD e REV sob a mesma chave de ensaio.
    '''
    hit_keys = ["sseqid", "qstart", "qend", "sstart", "send", "evalue", "pident", "qcovs", "qseq", "sseq", "sstrand"]
    hit_dict = {}
    with open(file, "r") as ifile:
        line = ifile.readline()
        line_num = 0
        while line != "":
            line_num += 1
            spl = line.strip().split("\t")
            if len(spl) < 12:
                line = ifile.readline()
                continue
                
            qseqid = spl[0]
            
            # Extrai a direção (fwd ou rev) do qseqid
            parts = qseqid.split("|")
            if len(parts) >= 2:
                # A chave do ensaio é o primeiro elemento (ex: "Primer")
                assay_key = parts[0]
                # A direção é o último elemento
                if parts[-1].lower() in ("fwd", "rev"):
                    dir = parts[-1].lower()
                else:
                    line = ifile.readline()
                    continue
            else:
                line = ifile.readline()
                continue
            
            # Inicializa o dicionário para esta chave se necessário
            if assay_key not in hit_dict:
                hit_dict[assay_key] = {"fwd": [], "rev": []}
            
            # Adiciona o hit
            hit_data = {x: y for x, y in zip(hit_keys, spl[1:])}
            hit_dict[assay_key][dir].append(hit_data)
            
            line = ifile.readline()
    return hit_dict

_WGS_CONTIG_RE = re.compile(r'^([A-Za-z]{4,6}\d{2})\d{6,9}$')

def _genome_key(sseqid):
    """
    Agrupa contigs que pertencem ao mesmo genoma montado, sem precisar de
    rede/NCBI: contigs de montagens WGS fragmentadas compartilham um prefixo
    de projeto+versao antes do numero sequencial do contig (ex:
    JBAMJC010000001.1 e JBAMJC010000002.1 sao dois contigs do MESMO genoma,
    prefixo "JBAMJC01"). Genomas com accession unico (ex: NZ_CP012345.1,
    cromossomo/plasmideo completo) nao batem no padrao WGS e usam o proprio
    accession como chave.
    """
    partes = sseqid.split('|')
    acc = partes[1] if len(partes) > 1 and partes[0].lower() in ['gb', 'ref', 'emb', 'dbj', 'gi'] else partes[0]
    acc = acc.split('.')[0]
    m = _WGS_CONTIG_RE.match(acc)
    return m.group(1) if m else acc


def _evaluate_hit_loc(hit_dict, primer_dict, tm_thresh = 45., size_max=9999, size_min=20, max_3prime_mm=0, Na=50, K=0, Tris=0, Mg=0, dNTPs=0, saltcorr=5):
    buffer_passing = "Assay_name_and_target,Forward_primer_seq,Reverse_primer_seq,Subject_ID,Tm_forward,Tm_reverse,Amplicon_size,Start,End,Raw_hits_no_genoma\n"
    buffer_all = "Assay_name_and_target,Forward_primer_seq,Reverse_primer_seq,Tm_forward,Tm_reverse,amplicon_size\n"

    for assay_num_target in hit_dict:
        fwd_seq, rev_seq = primer_dict[F"{assay_num_target}|fwd"], primer_dict[F"{assay_num_target}|rev"] # get primer sequences

        # 1) Agrupa por CONTIG exato (sseqid): _check_primer_quals so aceita
        #    um par se hit1.sseqid == hit2.sseqid (fwd e rev no mesmo contig,
        #    fitas opostas), entao comparar hits de contigs diferentes e
        #    sempre descarte garantido. Agrupar primeiro evita fazer o
        #    cross-product cego O(N_fwd x N_rev) inteiro so pra descartar.
        fwd_por_contig, rev_por_contig = {}, {}
        for hit in hit_dict[assay_num_target]["fwd"]:
            fwd_por_contig.setdefault(hit["sseqid"], []).append(hit)
        for hit in hit_dict[assay_num_target]["rev"]:
            rev_por_contig.setdefault(hit["sseqid"], []).append(hit)

        # Contagem bruta de hits (fwd+rev, mesmo sem par) por GENOMA -- e
        # barata (so len()) e da pra reportar "quantos matches reais esse
        # genoma teve" mesmo parando a validacao cedo la embaixo.
        genoma_de_contig = {}
        raw_hits_por_genoma = {}
        for sseqid in set(fwd_por_contig) | set(rev_por_contig):
            genoma = _genome_key(sseqid)
            genoma_de_contig[sseqid] = genoma
            n_hits = len(fwd_por_contig.get(sseqid, [])) + len(rev_por_contig.get(sseqid, []))
            raw_hits_por_genoma[genoma] = raw_hits_por_genoma.get(genoma, 0) + n_hits

        # 2) So contigs com hit nos dois sentidos podem virar um amplicon.
        #    Agrupa esses contigs por GENOMA pra que, assim que UM contig do
        #    genoma confirmar cobertura (par valido), os demais contigs
        #    desse MESMO genoma sejam pulados -- evita que um genoma
        #    fragmentado/multi-copia consuma toda a validacao e "afogue" os
        #    outros genomas do banco.
        contigs_por_genoma = {}
        for sseqid in set(fwd_por_contig) & set(rev_por_contig):
            contigs_por_genoma.setdefault(genoma_de_contig[sseqid], []).append(sseqid)

        for genoma, contigs in contigs_por_genoma.items():
            raw_hits_genoma = raw_hits_por_genoma.get(genoma, 0)
            achou_par_valido = False
            for sseqid in contigs:
                if achou_par_valido:
                    break
                for x in fwd_por_contig[sseqid]:
                    if achou_par_valido:
                        break
                    for y in rev_por_contig[sseqid]:
                        passing, tm_fwd, tm_rev, amp_size, threep_f_mm, threep_r_mm, start, end = _check_primer_quals(x, y, fwd_seq, rev_seq, tm_thresh=tm_thresh, size_max=size_max, size_min=size_min, max_3prime_mm=max_3prime_mm, Na=Na, K=K, Tris=Tris, Mg=Mg, dNTPs=dNTPs, saltcorr=saltcorr)
                        buffer_all += F"{assay_num_target},{fwd_seq},{rev_seq},{x['sseqid']},{tm_fwd},{tm_rev},{amp_size}\n"
                        if passing:
                            buffer_passing += F"{assay_num_target},{fwd_seq},{rev_seq},{x['sseqid']},{tm_fwd},{tm_rev},{amp_size},{start},{end},{raw_hits_genoma}\n"
                            achou_par_valido = True
                            break
    return buffer_passing, buffer_all

def _pull_amp_seqs(buffer_passing, fasta, log_file, Na=50, K=0, Tris=0, Mg=0, dNTPs=0, saltcorr=5):
    lines = buffer_passing.split("\n")[1:-1]
    seq_ids = [x.split(",")[3] for x in lines]
    unique_ids = set(seq_ids)
    # Below commented code may be faster, but is more storage-intensive
    # with open(log_file, "a") as log:
    #     subprocess.run("> contig_hits.temp", check=True, shell=True, stderr=log)
    #     for contig in unique_ids:
    #         commands = ['awk "/>${', contig, '}/{f=1; c=0} f; />/ && ++c==2{f=0}" ',  fasta, ' >> contig_hits.temp']
    #         print("".join(commands))
    #         subprocess.run("".join(commands), check=True, shell=True, stderr=log)
    seq_dict = {}
    count_found = 0
    # with open("contig_hits.temp", "r") as ifile:
    with open(fasta, "r") as ifile:
        line = ifile.readline()
        while line != "":
            if line != "" and line[0] == ">" and line[1:].split(" ")[0] in unique_ids:
                count_found += 1
                print(F"Number of records found: {count_found}/{len(unique_ids)}")
                header = line[1:].split(" ")[0]
                seq_dict[header] = ""
                line = ifile.readline()
                while line != "" and line[0] != ">":
                    seq_dict[header] = F"{seq_dict[header]}{line[:-1]}"
                    line = ifile.readline()
                if count_found == len(unique_ids):
                    break
            else:
                line = ifile.readline()

    buffer = "Assay_name_and_target,Forward_primer_seq,Reverse_primer_seq,Subject_ID,Tm_forward,Tm_reverse,Amplicon_size,Start,End,Amplicon_sequence,Amplicon_tm\n"
    for i in lines:
        spl = i.split(",")
        seq_id, start, stop = spl[3], int(spl[7]), int(spl[8])
        if start < stop:
            seq = seq_dict[seq_id][start-1:stop]
        else:
            seq = seq_dict[seq_id][stop-1:start]
        try:
            amp_tm = mt.Tm_NN(seq, nn_table = mt.DNA_NN4, Na=Na, K=K, Tris=Tris, Mg=Mg, dNTPs=dNTPs, saltcorr=saltcorr)
        except ValueError:
            amp_tm = 0.
        if stop < start:
            seq = Seq(seq).reverse_complement()
        buffer += F"{i},{seq},{amp_tm}\n"
    return buffer
