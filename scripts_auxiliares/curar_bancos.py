import os
import glob
import subprocess

DIRETORIO_ORIGEM = "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/refseq"
DIRETORIO_BLAST = "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/blast_dbs"
DIRETORIO_MANIFESTOS = "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/manifestos"

# Sequências identificadas na auditoria de agosto/2026 (tamanho de sequência
# anormal nos bancos combinados) como organismos fora do escopo de solo.
# O preparar_blast.py descarta o nome do organismo ao indexar (fica só o ID),
# por isso este script gera um manifesto accession -> organismo ANTES de
# tocar em qualquer arquivo, preservando essa informação para auditorias futuras.
ACCESSIONS_EXCLUIDAS = {
    "isopoda": {
        "OZ209255.1": "Anilocra frontalis (isópode parasita marinho de peixes)",
        "OZ209256.1": "Anilocra frontalis (isópode parasita marinho de peixes)",
        "OZ209257.1": "Anilocra frontalis (isópode parasita marinho de peixes)",
    },
    "platyhelminthes": {
        "CM097882.1": "Pseudobiceros splendidus (platelminto marinho)",
        "OZ249426.1": "Schmidtea nova (planária de água doce, não terrestre)",
    },
    "nematoda": {
        "CM075173.1": "Parascaris univalens (nematódeo parasita de equinos)",
    },
}

GRUPOS_AFETADOS = list(ACCESSIONS_EXCLUIDAS.keys())


def gerar_manifesto(taxon):
    pasta_alvo = os.path.join(DIRETORIO_ORIGEM, taxon)
    arquivos_fna = glob.glob(os.path.join(pasta_alvo, "**", "*.fna"), recursive=True)
    os.makedirs(DIRETORIO_MANIFESTOS, exist_ok=True)
    caminho_manifesto = os.path.join(DIRETORIO_MANIFESTOS, f"{taxon}.tsv")
    with open(caminho_manifesto, "w") as out:
        for fna in arquivos_fna:
            with open(fna, "r", errors="ignore") as f:
                for line in f:
                    if line.startswith(">"):
                        accession = line[1:].split(" ")[0].strip()
                        descricao = line[1:].strip()
                        out.write(f"{accession}\t{descricao}\n")
    print(f"  -> Manifesto salvo em {caminho_manifesto}")


def filtrar_e_reindexar(taxon):
    banidos = set(ACCESSIONS_EXCLUIDAS[taxon].keys())
    pasta_alvo = os.path.join(DIRETORIO_ORIGEM, taxon)
    arquivos_fna = glob.glob(os.path.join(pasta_alvo, "**", "*.fna"), recursive=True)
    base_out = os.path.join(DIRETORIO_BLAST, taxon)
    temp_fasta = os.path.join(pasta_alvo, "banco_curado.fasta")

    print(f"  -> Filtrando {len(banidos)} sequência(s) banida(s) de {len(arquivos_fna)} arquivo(s)...")
    removidos = 0
    with open(temp_fasta, "w") as outfile:
        for fna in arquivos_fna:
            manter = True
            with open(fna, "r", errors="ignore") as infile:
                for line in infile:
                    if line.startswith(">"):
                        accession = line[1:].split(" ")[0].strip()
                        manter = accession not in banidos
                        if not manter:
                            removidos += 1
                            continue
                        line = f"{line.split(' ')[0]}\n"
                    if manter:
                        outfile.write(line)

    print(f"  -> {removidos} sequência(s) removida(s).")

    for f in glob.glob(f"{base_out}*"):
        os.remove(f)

    comando = [
        "makeblastdb", "-in", temp_fasta, "-dbtype", "nucl",
        "-out", base_out, "-title", f"Banco {taxon.capitalize()} (curado)",
        "-parse_seqids",
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    os.remove(temp_fasta)
    if resultado.returncode == 0:
        print(f"✅ {taxon} reindexado com sucesso, sem os organismos fora de escopo.")
    else:
        print(f"❌ Erro ao reindexar {taxon}: {resultado.stderr}")


if __name__ == "__main__":
    print("PASSO 1/2: gerando manifestos (accession -> organismo) de todos os grupos baixados.")
    print("Isso preserva a identificação das espécies mesmo que os .fna sejam apagados depois,")
    print("já que o preparar_blast.py descarta essa informação ao indexar.\n")
    todos_grupos = [f.name for f in os.scandir(DIRETORIO_ORIGEM) if f.is_dir()]
    for taxon in todos_grupos:
        print(f"🧬 {taxon}")
        gerar_manifesto(taxon)

    print("\nPASSO 2/2: removendo organismos fora do escopo (solo) e reindexando os bancos afetados.\n")
    for taxon in GRUPOS_AFETADOS:
        print("-" * 50)
        print(f"🧹 Curando {taxon.upper()}...")
        for acc, motivo in ACCESSIONS_EXCLUIDAS[taxon].items():
            print(f"   - removendo {acc}: {motivo}")
        filtrar_e_reindexar(taxon)

    print("\n" + "=" * 60)
    print("🎉 CURADORIA CONCLUÍDA.")
    print("Bancos afetados: " + ", ".join(GRUPOS_AFETADOS))
    print("Rode 'blastdbcmd -db data/blast_dbs/<grupo> -info' para conferir a nova contagem.")
    print("=" * 60)
