import subprocess
import json

GRUPOS_TAXONOMICOS = [
    "Amoebozoa", 
    "Sar",         # Junta Stramenopiles, Alveolata e Rhizaria de uma vez só!
    "Excavata", 
    "Discoba",      # Substitutos modernos para Excavata
    "Metamonada"    # Substitutos modernos para Excavata
]

total_genomas = 0
total_refseq = 0
total_genbank = 0
bytes_refseq_total = 0
bytes_genbank_total = 0

print(f"{'TAXON':<16} | {'TOTAL':<6} | {'REFSEQ':<6} | {'GB (REF)':<8} | {'GENBANK':<7} | {'GB (GEN)'}")
print("-" * 75)

for taxon in GRUPOS_TAXONOMICOS:
    comando = [
        "datasets", "summary", "genome", "taxon", taxon,
        "--reference", 
        "--as-json-lines"
    ]
    
    try:
        resultado = subprocess.run(comando, capture_output=True, text=True)
        linhas = [linha for linha in resultado.stdout.strip().split('\n') if linha.strip()]
        
        qtd_total = 0
        qtd_refseq = 0
        qtd_genbank = 0
        bytes_refseq = 0
        bytes_genbank = 0
        
        for linha in linhas:
            dados = json.loads(linha)
            qtd_total += 1
            
            tamanho = 0
            if 'assembly_stats' in dados and 'total_sequence_length' in dados['assembly_stats']:
                tamanho = int(dados['assembly_stats']['total_sequence_length'])
                
            accession = dados.get("accession", "")
            if accession.startswith("GCF_"):
                qtd_refseq += 1
                bytes_refseq += tamanho
            elif accession.startswith("GCA_"):
                qtd_genbank += 1
                bytes_genbank += tamanho
                
        gb_refseq = bytes_refseq / (1024**3)
        gb_genbank = bytes_genbank / (1024**3)
        
        print(f"{taxon:<16} | {qtd_total:<6} | {qtd_refseq:<6} | {gb_refseq:<8.2f} | {qtd_genbank:<7} | {gb_genbank:.2f}")
        
        total_genomas += qtd_total
        total_refseq += qtd_refseq
        total_genbank += qtd_genbank
        bytes_refseq_total += bytes_refseq
        bytes_genbank_total += bytes_genbank
        
    except Exception as e:
        print(f"{taxon:<16} | ERRO AO CONSULTAR")

print("-" * 75)
print("🏆 PESO DETALHADO DO BANCO DE REFERÊNCIA:")
print(f"   -> Genomas Totais : {total_genomas}")
print(f"   -> Peso RefSeq    : {(bytes_refseq_total / (1024**3)):.2f} GB ({total_refseq} genomas)")
print(f"   -> Peso GenBank   : {(bytes_genbank_total / (1024**3)):.2f} GB ({total_genbank} genomas)")
print(f"   -> Peso Somado    : {((bytes_refseq_total + bytes_genbank_total) / (1024**3)):.2f} GB")
print("-" * 75)
