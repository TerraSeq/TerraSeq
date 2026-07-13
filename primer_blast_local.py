#!/usr/bin/env python

import argparse, time, os
import csv, io, subprocess
from Bio.Seq import Seq
from Bio.SeqUtils import MeltingTemp as mt

from reformat import _determine_primerfile_type, _check_and_read_valid_FASTA, _idt_to_fasta
# Retiramos o _pull_amp_seqs original da importação e mantemos os outros
from run_parse_blastn import _call_makeblastdb, _call_blastn, _blast_to_dict, _evaluate_hit_loc


# ==========================================
# FUNÇÃO DE EXTRAÇÃO BLINDADA (ATUALIZADA)
# ==========================================
def extrair_amplicons_via_blastdbcmd(csv_buffer, db_string, Na=50, K=0, Tris=0, Mg=1.5, dNTPs=0.6, saltcorr=7):
    """
    Usa o blastdbcmd para extrair sequências, limpa o texto, calcula a Tm e expõe erros.
    """
    print("🎣 Extraindo sequências dos amplicons direto da memória (blastdbcmd)...")
    reader = csv.DictReader(io.StringIO(csv_buffer))
    fieldnames = list(reader.fieldnames)
    
    if "Amplicon_sequence" not in fieldnames:
        fieldnames.append("Amplicon_sequence")
    if "amplicon_tm" not in fieldnames:
        fieldnames.append("amplicon_tm")
        
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    for row in reader:
        # 1. Busca flexível da coluna do ID (Subject_ID)
        acc_raw = row.get("Subject_ID", "")
        if not acc_raw:
            for col in row.keys():
                if col and "id" in col.lower() and "subject" in col.lower():
                    acc_raw = row[col]
                    break
                    
        # 2. Extração inteligente do ID (Lidando com prefixos do NCBI)
        partes = acc_raw.split("|")
        # Se vier no formato ref|NZ_...| ou gb|NZ_...|
        if len(partes) > 1 and partes[0].lower() in ["ref", "gb", "emb", "dbj", "gi", ""]:
            acc = partes[1].strip() # Pega o verdadeiro ID, ignorando o prefixo
        else:
            acc = partes[0].strip()
        
        # 3. Extrator flexível de posições (ignora maiúsculas e minúsculas)
        start = 0
        end = 0
        for col, val in row.items():
            if col and val:
                col_lower = col.lower()
                if start == 0 and ("start" in col_lower or "sstart" in col_lower):
                    try: start = int(float(val))
                    except ValueError: pass
                if end == 0 and ("end" in col_lower or "send" in col_lower):
                    try: end = int(float(val))
                    except ValueError: pass
                    
        # Se as coordenadas ainda forem 0, nós evitamos o crash do blastdbcmd
        if start <= 0 or end <= 0:
            with open("erros_blastdbcmd.txt", "a") as f_err:
                f_err.write(f"Coordenadas invalidas para {acc}: start={start}, end={end}\n")
            row["Amplicon_sequence"] = "N/A"
            row["amplicon_tm"] = "N/A"
            writer.writerow(row)
            continue
            
        if start > end:
            range_str = f"{end}-{start}"
            strand = "minus"
        else:
            range_str = f"{start}-{end}"
            strand = "plus"
            
        # 4. O pulo do gato: ID limpo e protegido por aspas simples ('{acc}')
        comando_shell = f"blastdbcmd -db \"{db_string}\" -entry '{acc}' -range {range_str} -strand {strand} -outfmt %s"
        
        try:
            res = subprocess.run(comando_shell, shell=True, capture_output=True, text=True, check=True)
            seq = res.stdout.strip().replace('\n', '').replace('\r', '')
            
            if seq and not seq.lower().startswith("error"):
                row["Amplicon_sequence"] = seq
                try:
                    # Calcula a Tm usando a biblioteca Biopython
                    tm_val = mt.Tm_NN(Seq(seq), Na=Na, K=K, Tris=Tris, Mg=Mg, dNTPs=dNTPs, saltcorr=saltcorr)
                    row["amplicon_tm"] = round(tm_val, 2)
                except Exception:
                    row["amplicon_tm"] = "N/A"
            else:
                with open("erros_blastdbcmd.txt", "a") as f_err:
                    f_err.write(f"Aviso em {acc}: Saida vazia ou erro no retorno: {seq}\n")
                row["Amplicon_sequence"] = "N/A"
                row["amplicon_tm"] = "N/A"
                
        except subprocess.CalledProcessError as e:
            with open("erros_blastdbcmd.txt", "a") as f_err:
                f_err.write(f"Falha critica em {acc} | Comando: {comando_shell}\nErro: {e.stderr.strip()}\n")
            row["Amplicon_sequence"] = "N/A"
            row["amplicon_tm"] = "N/A"
            
        writer.writerow(row)
        
    return output.getvalue()
# ==========================================


parser = argparse.ArgumentParser()
parser.add_argument("-g", "--genomes", type=str, help="FASTA formatted file containing concatenated genome records. It may be helpful to include the genome name in each record header.")
parser.add_argument("-p", "--primers", type=str, help="A FASTA containing primer sequences OR an excel file output by IDT PrimerQuest. If a FASTA, records should be formatted without spaces like >Assay_Name(unique)|Target_Name|Direction(fwd|rev)")
parser.add_argument("-o", "--out", type=str, help="Path and prefix of outputs.")
parser.add_argument("-m", "--tm_thresh", type=float, default=45., help="Minimum melting temperature at which primers should be included. (default:45.)")
parser.add_argument("-e", "--evalue", type=float, default=10., help="Maximum e-value of BLAST hits to evaluate. (default:10)")
parser.add_argument("-t", "--n_threads", type=int, default=1, help="Number of threads to use for BLASTN. (default:1)")
parser.add_argument("--min_size", type=int, default=20, help="Minimum amplicon size to include in results. (default:20)")
parser.add_argument("--max_size", type=int, default=9999, help="Maximum amplicon size to include in results. (default:9999)")
parser.add_argument("--max_target_seqs", type=int, default=30000, help="Maximum number of BLAST hits to return. Lower values speed up parsing. (default:30000)")
parser.add_argument("--max_3prime_mismatches", type=int, default=0, help="Maximum allowed mismatches in the last 5 bp of the 3' end. NCBI uses 2. (default:0)")
parser.add_argument("--qcov_hsp_perc", type=float, default=0, help="Minimum query coverage per HSP. (default:0, no filter)")
parser.add_argument("--na", type=float, default=50., help="Sodium concentration, in millimolar. (default:50)")
parser.add_argument("-k", "--pot", type=float, default=0., help="Potassium concentration, in millimolar. (default:0)")
parser.add_argument("--tris", type=float, default=0., help="Tris concentration, in millimolar. (default:0)")
parser.add_argument("--mg", type=float, default=0., help="Magnesium concentration, in millimolar. (default:0)")
parser.add_argument("--dntps", type=float, default=0, help="dNTP concentration, in millimolar. (default:0)")
parser.add_argument("--saltcorr", type=int, default=5, help="Salt correction method. See https://biopython.org/docs/1.75/api/Bio.SeqUtils.MeltingTemp.html#Bio.SeqUtils.MeltingTemp.salt_correction  (default: 5)")
parser.add_argument("--no_blast", action="store_true", help="If specified, don't rerun blast but just change parameters for matches.")
parser.add_argument("--use_existing_db", action="store_true", help="If specified, don't rebuild the database.")
parser.add_argument("--amp_seq", action="store_true", help="If specified, include the sequence of the amplicon.")
args = parser.parse_args()

log_file = F"primer_blast_local_{time.strftime('%Y-%m-%d_%H-%M-%S')}.stderr.log"

#Check the inputs
# 1. Comentamos a verificação do FASTA, pois agora usamos os bancos indexados diretos!
# if not args.use_existing_db:
#     print("Verifying genome file...")
#     if not _check_and_read_valid_FASTA(args.genomes):
#         raise ValueError("Please verify that the genomes file is in FASTA format.")
#     print("Genome file verfied...")

print("Verifying primer file...")
primerfile_type = _determine_primerfile_type(args.primers)
if primerfile_type == None:
    raise ValueError("Please verify that the primer file type is a valid XLS or FASTA file.")
if primerfile_type == "EXCEL":
    buffer, primer_dict = _idt_to_fasta(args.primers)
    primer_fasta = os.path.splitext(args.primers)[0] + "__formatted.fasta"
    with open(primer_fasta, "w") as ofile:
        ofile.write(buffer)
else:
    primer_fasta = args.primers
    qual, primer_dict = _check_and_read_valid_FASTA(primer_fasta, primers = True)
    if not qual:
        raise ValueError("Please reformat the primer file as specified in the help.")
print("Primer file verified...")

if not os.path.isdir(os.path.dirname(args.out)) and os.path.dirname(args.out) != "":
    os.mkdir(os.path.dirname(args.out))

# call commands
print("Running BLASTn...")
blast_out = args.out + "__blastn.out"

if not args.no_blast:
    # 2. A MÁGICA: Passamos a string de bancos direto pro BLAST!
    # Envolvemos em ASPAS DUPLAS para o terminal Linux não se perder nos espaços
    blast_db = f'"{args.genomes}"' 
    _call_blastn(primer_fasta, blast_db, args.n_threads, args.evalue, args.max_target_seqs, args.qcov_hsp_perc, log_file, blast_out)
    
print("BLASTn finished...")
print("Parsing results...")
blast_d = _blast_to_dict(blast_out)
buffer_passing, buffer_all = _evaluate_hit_loc(blast_d, primer_dict, tm_thresh=args.tm_thresh, size_max=args.max_size, size_min=args.min_size, max_3prime_mm=args.max_3prime_mismatches, Na=args.na, K=args.pot, Tris=args.tris, Mg=args.mg, dNTPs=args.dntps, saltcorr=args.saltcorr)

# 3. Chama a NOSSA função blindada para extrair as sequências
if args.amp_seq:
    buffer_passing = extrair_amplicons_via_blastdbcmd(
        buffer_passing, 
        args.genomes, 
        Na=args.na, K=args.pot, Tris=args.tris, Mg=args.mg, dNTPs=args.dntps, saltcorr=args.saltcorr
    )

with open(args.out + "__results.pass.csv", "w") as ofile:
    ofile.write(buffer_passing)
with open(args.out + "__results.all.csv", "w") as ofile:
    ofile.write(buffer_all)
print("Finished parsing results...")
