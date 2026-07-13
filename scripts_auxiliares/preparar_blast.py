import os
import subprocess
import glob

DIRETORIO_ORIGEM = "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/refseq"
DIRETORIO_BLAST = "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/blast_dbs"
os.makedirs(DIRETORIO_BLAST, exist_ok=True)

print("🚀 Iniciando indexação PROFISSIONAL (Modo Arquivo Físico)...\n")

pastas_taxons = [f.name for f in os.scandir(DIRETORIO_ORIGEM) if f.is_dir()]

for taxon in pastas_taxons:
    print("-" * 50)
    print(f"🧬 Processando o grupo: {taxon.upper()}")
    
    pasta_alvo = os.path.join(DIRETORIO_ORIGEM, taxon)
    base_out = os.path.join(DIRETORIO_BLAST, taxon)
    
    # Verifica se o banco já foi criado
    if os.path.exists(f"{base_out}.nsq"):
        print(f"✅ Banco de {taxon} já existe. Pulando...")
        continue

    # Encontra arquivos .fna
    caminho_busca = os.path.join(pasta_alvo, "**", "*.fna")
    arquivos_fna = glob.glob(caminho_busca, recursive=True)
    
    if not arquivos_fna:
        print(f"⚠️ Nenhum arquivo .fna encontrado para {taxon}.")
        continue

    # 1. Cria um arquivo único físico (Garante integridade e leitura de cabeçalhos)
    temp_fasta = os.path.join(pasta_alvo, "banco_completo.fasta")
    print(f"  -> Concatenando {len(arquivos_fna)} arquivos em arquivo único...")
    
    with open(temp_fasta, "w") as outfile:
        for fna in arquivos_fna:
            with open(fna, 'r', errors='ignore') as infile:
                for line in infile:
                    if line.startswith(">"):
                        # Vamos reduzir o cabeçalho apenas ao ID, nada mais
                        # NC_000917.1 Archaeoglobus -> >NC_000917.1
                        id_purificado = line.split(" ")[0]
                        line = f"{id_purificado}\n"
                    outfile.write(line)
    
    # 2. Comando profissional de indexação
    comando = [
        "makeblastdb",
        "-in", temp_fasta,
        "-dbtype", "nucl",
        "-out", base_out,
        "-title", f"Banco {taxon.capitalize()}",
        "-parse_seqids"
    ]
    
    print(f"  -> Executando makeblastdb...")
    resultado = subprocess.run(comando, capture_output=True, text=True)
    
    if resultado.returncode == 0:
        print(f"✅ Banco de {taxon} indexado com SUCESSO!")
    else:
        print(f"❌ Erro em {taxon}: {resultado.stderr}")
    
    # 3. Limpeza
    if os.path.exists(temp_fasta):
        os.remove(temp_fasta)

print("\n" + "=" * 60)
print("🎉 BANCOS INDEXADOS E PRONTOS PARA EXTRAÇÃO!")
print("Use o comando 'blastdbcmd -db ... -info' para confirmar os IDs.")
print("=" * 60)
