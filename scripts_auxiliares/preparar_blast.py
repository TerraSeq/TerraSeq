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
    
    # Verifica se o banco já foi criado. Bancos grandes o suficiente viram
    # MULTI-VOLUME (base_out.00.nsq, base_out.01.nsq, ...) em vez de um
    # único base_out.nsq -- checar só ".nsq" não detecta esses, e o script
    # tentaria reconstruir do zero a partir do data/refseq BRUTO (sem a
    # curadoria de organismos fora de escopo já aplicada pelo
    # curar_bancos.py), apagando essa curadoria sem aviso nenhum.
    ja_existe = os.path.exists(f"{base_out}.nsq") or os.path.exists(f"{base_out}.00.nsq")
    if ja_existe:
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
    # -max_file_sz: sem isso, o makeblastdb usa o padrão de ~1GiB por volume,
    # e bancos grandes (dezenas/centenas de GB) viram dezenas ou CENTENAS de
    # volumes (.00.nsq, .01.nsq, ...). O coleoptera (421GB) chegou a 107
    # volumes e isso quebrou o blastn: "Error pre-fetching sequence data"
    # (BLAST Database error), retornando sseqid="Unknown"/coordenadas
    # zeradas pra 100% dos hits, sem nenhum erro fatal -- silencioso.
    # Testamos: araneae com 70 volumes e gastropoda com 89 funcionam bem,
    # coleoptera com 107 falha 100% -- o limite real do BLAST+ fica em
    # algum ponto entre 90 e 106 volumes. O makeblastdb exige
    # -max_file_sz < 4GiB (rejeita valores maiores), então usamos o maior
    # valor permitido pra minimizar o número de volumes.
    comando = [
        "makeblastdb",
        "-in", temp_fasta,
        "-dbtype", "nucl",
        "-out", base_out,
        "-title", f"Banco {taxon.capitalize()}",
        "-parse_seqids",
        "-max_file_sz", "3900MB",
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
