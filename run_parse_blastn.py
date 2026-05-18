#!/usr/bin/env python
from Bio.SeqUtils import MeltingTemp as mt
from Bio.Seq import Seq
from reformat import _decode_fasta_header
import numpy as np
import subprocess, os

def _other_dir(dir):
    if dir == "fwd":
        return "rev"
    else:
        return "fwd"
def _count_matches(seq1, seq2, shift = 0):
    count = 0
    for i in range(min([len(seq1), len(seq2)])):
        if i+shift < len(seq1) and seq1[i+shift] == seq2[i]:
            count += 1
    return count


def _find_3prime_mms(pseq, aseq): # find 3' end mismatches between primer and aligned sequence
    match_ct_arr = np.zeros(len(pseq))
    for shift in range(len(pseq)):
        match_ct_arr[shift] = _count_matches(pseq, aseq, shift = shift)
    best_shift = np.argmax(match_ct_arr)
    return len(pseq)+best_shift - len(aseq)

def _count_3prime_mms_in_last_5(pseq, aseq):
    """Conta mismatches nos últimos 5 bp da extremidade 3'"""
    last_5_p = pseq[-5:] if len(pseq) >= 5 else pseq
    last_5_a = aseq[-5:] if len(aseq) >= 5 else aseq
    return sum(1 for p, a in zip(last_5_p, last_5_a) if p != a)

def _check_primer_quals(hit1, hit2, fwd_seq, rev_seq, tm_thresh = 45., size_max=9999, size_min=20, max_3prime_mm=0, Na=50, K=0, Tris=0, Mg=0, dNTPs=0, saltcorr=5):
    if hit1["sseqid"] == hit2["sseqid"] and hit1["sstrand"] != hit2["sstrand"]: # Check opposite strand annealing
        end_diff = int(hit2["sstart"]) - int(hit1["sstart"]) # amplicon size
        if (hit1["sstrand"] == "plus" and end_diff > 0) or (hit1["sstrand"] == "minus" and end_diff < 0): # primers are convergent
            try:
                if hit1["qseq"] == hit1["sseq"]:
                    tm_fwd = mt.Tm_NN(hit1["qseq"], nn_table = mt.DNA_NN4, Na=Na, K=K, Tris=Tris, Mg=Mg, dNTPs=dNTPs, saltcorr=saltcorr)
                else:
                    tm_fwd = mt.Tm_NN(hit1["qseq"], c_seq = Seq(hit1["sseq"]).reverse_complement(), nn_table = mt.DNA_NN4, Na=Na, K=K, Tris=Tris, Mg=Mg, dNTPs=dNTPs, saltcorr=saltcorr)
            except ValueError:
                tm_fwd = 0
            try:
                if hit2["qseq"] == hit2["sseq"]:
                    tm_rev = mt.Tm_NN(hit2["qseq"], nn_table = mt.DNA_NN4, Na=Na, K=K, Tris=Tris, Mg=Mg, dNTPs=dNTPs, saltcorr=saltcorr)
                else:
                    tm_rev = mt.Tm_NN(hit2["qseq"], c_seq = Seq(hit2["sseq"]).reverse_complement(), nn_table = mt.DNA_NN4, Na=Na, K=K, Tris=Tris, Mg=Mg, dNTPs=dNTPs, saltcorr=saltcorr)
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

def _call_blastn(query, db, nt, ev, max_target_seqs, qcov_hsp_perc, log_file, out_file):
    cmd = F"blastn -query {query} -db {db} -num_threads {nt} -word_size 7 -evalue {ev} -outfmt \"6 qseqid sseqid qstart qend sstart send evalue pident qcovs qseq sseq sstrand\" -max_target_seqs {max_target_seqs}"
    
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

def _evaluate_hit_loc(hit_dict, primer_dict, tm_thresh = 45., size_max=9999, size_min=20, max_3prime_mm=0, Na=50, K=0, Tris=0, Mg=0, dNTPs=0, saltcorr=5):
    buffer_passing, buffer_all = "Assay_name_and_target,Forward_primer_seq,Reverse_primer_seq,Subject_ID,Tm_forward,Tm_reverse,Amplicon_size,Start,End\n", "Assay_name_and_target,Forward_primer_seq,Reverse_primer_seq,Tm_forward,Tm_reverse,amplicon_size\n"
    for assay_num_target in hit_dict:
        for x in hit_dict[assay_num_target]["fwd"]:
            for y in hit_dict[assay_num_target]["rev"]:
                fwd_seq, rev_seq = primer_dict[F"{assay_num_target}|fwd"], primer_dict[F"{assay_num_target}|rev"] # get primer sequences
                passing, tm_fwd, tm_rev, amp_size, threep_f_mm, threep_r_mm, start, end = _check_primer_quals(x, y, fwd_seq, rev_seq, tm_thresh=tm_thresh, size_max=size_max, size_min=size_min, max_3prime_mm=max_3prime_mm, Na=Na, K=K, Tris=Tris, Mg=Mg, dNTPs=dNTPs, saltcorr=saltcorr)
                if passing:
                    buffer_passing += F"{assay_num_target},{fwd_seq},{rev_seq},{x['sseqid']},{tm_fwd},{tm_rev},{amp_size},{start},{end}\n"
                buffer_all += F"{assay_num_target},{fwd_seq},{rev_seq},{x['sseqid']},{tm_fwd},{tm_rev},{amp_size}\n"
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
