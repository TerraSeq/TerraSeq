import os
import time
from Bio import Entrez

# Configure seu email
Entrez.email = "tiagogabriel3542@gmail.com"

# Tabela de Termos de Busca NCBI para TODOS os grupos
# Focando em sequências RefSeq, GenBank completos e cromossomos/mitocôndrias
BANCOS_PARA_BAIXAR = {
    # --- MICRORGANISMOS (Bancos gigantes) ---
    "fungi_all.fasta": 'Fungi[Organism] AND (refseq[filter] OR "complete genome"[Title])',
    "protozoa_all.fasta": 'Protozoa[Organism] AND (refseq[filter] OR "complete genome"[Title])',
    "bacteria_all.fasta": 'Bacteria[Organism] AND (refseq[filter] OR "complete genome"[Title])',
    "archaea_all.fasta": 'Archaea[Organism] AND (refseq[filter] OR "complete genome"[Title])',
    "virus_all.fasta": 'Viruses[Organism] AND (refseq[filter] OR "complete genome"[Title])',

    # --- MICROFAUNA ---
    "nematoda_all.fasta": 'Nematoda[Organism] AND (refseq[filter] OR "complete genome"[Title])',
    "tardigrada_all.fasta": 'Tardigrada[Organism] AND ("complete genome"[Title] OR "chromosome"[Title])',
    "rotifera_all.fasta": 'Rotifera[Organism] AND ("complete genome"[Title] OR "chromosome"[Title])',

    # --- MESOFAUNA ---
    "acari_all.fasta": 'Acari[Organism] AND (refseq[filter] OR "complete genome"[Title])',
    "collembola_all.fasta": 'Collembola[Organism] AND (refseq[filter] OR "complete genome"[Title])',

    # --- MACROFAUNA E ENGENHEIROS ---
    "minhocas_all.fasta": 'Crassiclitellata[Organism] AND ("complete genome"[Title] OR "mitochondrion"[Title])',
    "formicidae_all.fasta": 'Formicidae[Organism] AND (refseq[filter] OR "complete genome"[Title])',
    "termitoidae_all.fasta": 'Isoptera[Organism] AND (refseq[filter] OR "complete genome"[Title])',
    "isopoda_all.fasta": 'Isopoda[Organism] AND ("complete genome"[Title] OR "mitochondrion"[Title])',
    "myriapoda_all.fasta": 'Myriapoda[Organism] AND ("complete genome"[Title] OR "mitochondrion"[Title])',
    "platelmintos_all.fasta": 'Platyhelminthes[Organism] AND (refseq[filter] OR "complete genome"[Title] OR "mitochondrion"[Title])',
    "aracnideos_all.fasta": 'Arachnida[Organism] AND (refseq[filter] OR "complete genome"[Title] OR "mitochondrion"[Title])',
    "insetos_all.fasta": 'Insecta[Organism] AND (refseq[filter] OR "complete genome"[Title])',
    "moluscos_all.fasta": 'Mollusca[Organism] AND (refseq[filter] OR "complete genome"[Title] OR "mitochondrion"[Title])',

    # --- FLORA E MEGAFAUNA ---
    "plantas_all.fasta": 'Viridiplantae[Organism] AND (refseq[filter] OR "complete genome"[Title])',
    "megafauna_all.fasta": 'Vertebrata[Organism] AND (refseq[filter] OR "complete genome"[Title])'
}

pasta_destino = os.path.join(os.path.dirname(__file__), "data", "refseq")
os.makedirs(pasta_destino, exist_ok=True)

print("🚀 Iniciando Motor de Download de Genomas do Solo...")
print(f"Total de bancos na fila: {len(BANCOS_PARA_BAIXAR)}")

for arquivo, query in BANCOS_PARA_BAIXAR.items():
    caminho_arquivo = os.path.join(pasta_destino, arquivo)
    
    if os.path.exists(caminho_arquivo):
        print(f"⏩ {arquivo} já existe. Pulando...")
        continue
        
    print(f"\n🔍 Buscando {arquivo} -> Query: {query}")
    try:
        # 1. Pesquisa quantos IDs existem
        # Usando retmax=5000 para limitar o tamanho dos arquivos e agilizar o pipeline
        handle = Entrez.esearch(db="nucleotide", term=query, retmax=5000)
        record = Entrez.read(handle)
        handle.close()
        
        ids = record["IdList"]
        total = len(ids)
        print(f"🧬 Encontrados {total} genomas/cromossomos (Limitado a max 5000).")
        
        if total == 0:
            print("⚠️ Aviso: Nenhum registro de alta qualidade encontrado com essa query.")
            with open(caminho_arquivo, "w") as f:
                f.write(">Nenhum_registro_encontrado\nN\n")
            continue
            
        print(f"⏳ Baixando sequências FASTA para {arquivo}...")
        
        # 2. Baixa o FASTA em lotes de 100 para não estourar a memória
        with open(caminho_arquivo, "w") as out_handle:
            batch_size = 100
            for start in range(0, total, batch_size):
                fim = min(total, start + batch_size)
                print(f"   📥 Baixando {start+1} até {fim} de {total}...")
                
                fetch_handle = Entrez.efetch(db="nucleotide", id=ids[start:fim], rettype="fasta", retmode="text")
                out_handle.write(fetch_handle.read())
                fetch_handle.close()
                
                # Respeitar o limite da API do NCBI (máximo de 3 a 10 requisições por segundo)
                time.sleep(1) 
                
        print(f"✅ Download de {arquivo} concluído!")
        
    except Exception as e:
        print(f"❌ Erro ao processar {arquivo}: {e}")

print("\n🎉 Todos os downloads finalizados! O servidor está pronto para rodar o pipeline.")
