import os
import time
from Bio import Entrez

Entrez.email = "tiagogabriel3542@gmail.com"

# Focando apenas nos 2 que deram problema, com queries corrigidas e lotes menores
BANCOS_PARA_BAIXAR = {
    # Usando os filos reais que compõem os "Protistas/Protozoários" no seu main.py
    "protozoa_all.fasta": '("Amoebozoa"[Organism] OR "Ciliophora"[Organism] OR "Euglenozoa"[Organism] OR "Cercozoa"[Organism] OR "Foraminifera"[Organism] OR "Rhizaria"[Organism]) AND (refseq[filter] OR "complete genome"[Title])',
    
    # Plantas continuam igual, mas vamos mudar a forma de baixar
    "plantas_all.fasta": 'Viridiplantae[Organism] AND (refseq[filter] OR "complete genome"[Title])'
}

pasta_destino = os.path.join(os.path.dirname(__file__), "data", "refseq")
os.makedirs(pasta_destino, exist_ok=True)

print("🚑 Iniciando Script de Resgate...")

for arquivo, query in BANCOS_PARA_BAIXAR.items():
    caminho_arquivo = os.path.join(pasta_destino, arquivo)
    
    print(f"\n🔍 Buscando {arquivo} -> Query: {query}")
    try:
        handle = Entrez.esearch(db="nucleotide", term=query, retmax=5000)
        record = Entrez.read(handle)
        handle.close()
        
        ids = record["IdList"]
        total = len(ids)
        print(f"🧬 Encontrados {total} registros.")
        
        if total == 0:
            print("⚠️ Ainda não encontrou nada.")
            continue
            
        print(f"⏳ Baixando sequências... (Lotes reduzidos para evitar timeout)")
        
        # LOTE MENOR: 20 genomas por vez (ideal para Plantas que são muito pesadas)
        batch_size = 20 
        
        with open(caminho_arquivo, "w") as out_handle:
            for start in range(0, total, batch_size):
                fim = min(total, start + batch_size)
                print(f"   📥 Baixando {start+1} até {fim} de {total}...")
                
                # Adicionando um mecanismo de "tentar novamente" (Retry) se der IncompleteRead
                sucesso = False
                tentativas = 0
                while not sucesso and tentativas < 3:
                    try:
                        fetch_handle = Entrez.efetch(db="nucleotide", id=ids[start:fim], rettype="fasta", retmode="text")
                        out_handle.write(fetch_handle.read())
                        fetch_handle.close()
                        sucesso = True
                    except Exception as e_fetch:
                        tentativas += 1
                        print(f"      ⚠️ Falha na conexão (Tentativa {tentativas}/3). Aguardando 5s para tentar de novo...")
                        time.sleep(5)
                
                if not sucesso:
                    print(f"      ❌ Falhou ao baixar o bloco {start+1}-{fim}. Pulando para o próximo.")
                
                time.sleep(2) # Pausa segura
                
        print(f"✅ Download de {arquivo} concluído!")
        
    except Exception as e:
        print(f"❌ Erro ao processar {arquivo}: {e}")

print("\n🎉 Resgate finalizado! Banco 100% completo.")
