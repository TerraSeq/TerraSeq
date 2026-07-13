import subprocess
import os
import json
import zipfile

# Apenas os grupos leves (abaixo de 100 GB)
GRUPOS_LEVES = [
    "amoebozoa", 
    "sar", 
    "discoba", 
    "metamonada"
]

# Caminho absoluto definido para salvar no SSD
DIRETORIO_DESTINO = "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/refseq"
os.makedirs(DIRETORIO_DESTINO, exist_ok=True)

print(f"🚀 Iniciando download ROBUSTO (Retomável) para o SSD...\n")
print(f"📂 Destino: {DIRETORIO_DESTINO}\n")

for taxon in GRUPOS_LEVES:
    pasta_taxon = os.path.join(DIRETORIO_DESTINO, taxon)
    arquivo_zip = os.path.join(DIRETORIO_DESTINO, f"{taxon}.zip")
    
    print("-" * 60)
    print(f"📥 Processando {taxon.upper()}...")
    
    # PASSO 1: Baixar o pacote "desidratado" (se já não existir a pasta)
    if not os.path.exists(pasta_taxon):
        comando_zip = [
            "datasets", "download", "genome", "taxon", taxon,
            "--assembly-source", "all",
            "--reference", 
            "--dehydrated", # O segredo para o download retomável
            "--filename", arquivo_zip
        ]
        
        try:
            print("   -> Obtendo metadados do NCBI...")
            subprocess.run(comando_zip, check=True, capture_output=True)
            
            # Extraindo o ZIP para a pasta do taxon
            with zipfile.ZipFile(arquivo_zip, 'r') as zip_ref:
                zip_ref.extractall(pasta_taxon)
            
            # Apaga o arquivo ZIP para economizar espaço, já que extraímos
            os.remove(arquivo_zip)
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro ao baixar metadados de {taxon}: {e}")
            continue

    # PASSO 2: Reidratar (Baixar os arquivos pesados de fato). 
    # É este comando que pode ser interrompido e retomado sem perder dados!
    print("   -> Baixando sequências (Rehydrate) - Isso pode demorar e é retomável...")
    comando_rehydrate = ["datasets", "rehydrate", "--directory", pasta_taxon]
    
    try:
        subprocess.run(comando_rehydrate, check=True)
    except subprocess.CalledProcessError:
        print(f"⚠️ O download de {taxon} foi interrompido ou falhou. Rode o script novamente para retomar.")
        continue
        
    # PASSO 3: Validação e Contagem
    # Vamos ler o relatório do NCBI gerado dentro da pasta para contar exatamente o que baixou
    relatorio_jsonl = os.path.join(pasta_taxon, "ncbi_dataset", "data", "assembly_data_report.jsonl")
    
    qtd_refseq = 0
    qtd_genbank = 0
    
    if os.path.exists(relatorio_jsonl):
        with open(relatorio_jsonl, 'r') as f:
            for linha in f:
                if not linha.strip(): continue
                dados = json.loads(linha)
                accession = dados.get("accession", "")
                if accession.startswith("GCF_"):
                    qtd_refseq += 1
                elif accession.startswith("GCA_"):
                    qtd_genbank += 1
                    
        total = qtd_refseq + qtd_genbank
        print(f"✅ {taxon.upper()} CONCLUÍDO!")
        print(f"   📊 Validação: Baixados {total} genomas (RefSeq: {qtd_refseq} | GenBank: {qtd_genbank})")
    else:
        print(f"✅ {taxon.upper()} baixado, mas não foi possível ler o relatório para contagem.")

print("\n" + "=" * 60)
print("🎉 TODOS OS DOWNLOADS LEVES FORAM PROCESSADOS!")
print("=" * 60)
