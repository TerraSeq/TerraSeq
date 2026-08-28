import subprocess
import os
import json
import zipfile

# Baixa os fungos divididos por FILO, em vez do reino "Fungi" inteiro de uma
# vez -- os mesmos 6 filos que o motor de classificacao ecologica
# (classificar_ecologia em main.py) ja espera reconhecer como "Fungos"
# (Microrganismos). Baixar separado por filo, em pastas com esses nomes
# exatos, faz com que cada um vire um grupo proprio em data/refseq/<filo>,
# seja indexado automaticamente em data/blast_dbs/<filo> e entre sozinho
# nos bancos combinados (refseqsoil/eucariotos), igual aos outros 18 grupos.
#
# ATENCAO -- o NCBI Datasets nao tem filtro por habitat (so por taxonomia),
# entao isso vai trazer fungos NAO-solo tambem (leveduras de laboratorio,
# patogenos humanos, fungos marinhos, liquens, etc.) -- depois de baixar,
# repetir o mesmo processo de curadoria que ja fizemos pros grupos animais:
#   1. python3 scripts_auxiliares/gerar_manifesto_taxid.py
#   2. python3 scripts_auxiliares/listar_organismos_por_grupo.py
#   3. python3 scripts_auxiliares/detectar_habitat_suspeito.py
#   4. revisar e excluir via curar_bancos.py (TAXIDS_EXCLUIDOS)
#
# ATENCAO 2 -- Ascomycota e Basidiomycota sao filos ENORMES (podem ser
# maiores que "bacteria", que ja tem >22 mil genomas). Se o espaco em disco
# for uma preocupacao, considerem comentar essas duas linhas de
# GRUPOS_FUNGOS abaixo e rodar primeiro so os filos menores (Glomeromycota,
# Zoopagomycota, Mucoromycota, Chytridiomycota), que sao mais
# especificamente associados a solo (micorrizas, fungos-armadilha de
# nematoide, etc.) e bem mais leves.

GRUPOS_FUNGOS = [
    "glomeromycota",     # fungos micorrizicos arbusculares -- obrigatoriamente associados a raiz/solo
    "zoopagomycota",      # inclui fungos-armadilha de nematoide e parasitas de outros microrganismos do solo
    "mucoromycota",       # bolores de solo (Mucorales) + parte dos micorrizicos
    "chytridiomycota",    # fungos zoosporicos, varios de solo umido
    "basidiomycota",      # GRANDE -- inclui cogumelos decompositores de solo/serrapilheira, mas tambem ferrugens/carvoes de planta
    "ascomycota",         # MUITO GRANDE -- maior filo fungico, mistura extrema de habitats (solo, patogenos, leveduras, liquens, marinho)
]

DIRETORIO_DESTINO = "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/refseq"
os.makedirs(DIRETORIO_DESTINO, exist_ok=True)

print(f"🚀 Iniciando download ROBUSTO (Retomável) dos filos de Fungos...\n")
print(f"📂 Destino: {DIRETORIO_DESTINO}\n")

for taxon in GRUPOS_FUNGOS:
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
            "--dehydrated",  # O segredo para o download retomável
            "--filename", arquivo_zip
        ]

        try:
            print("   -> Obtendo metadados do NCBI...")
            subprocess.run(comando_zip, check=True, capture_output=True)

            with zipfile.ZipFile(arquivo_zip, 'r') as zip_ref:
                zip_ref.extractall(pasta_taxon)

            os.remove(arquivo_zip)

        except subprocess.CalledProcessError as e:
            print(f"❌ Erro ao baixar metadados de {taxon}: {e}")
            continue

    # PASSO 2: Reidratar (Baixar os arquivos pesados de fato).
    print("   -> Baixando sequências (Rehydrate) - Isso pode demorar e é retomável...")
    comando_rehydrate = ["datasets", "rehydrate", "--directory", pasta_taxon]

    try:
        subprocess.run(comando_rehydrate, check=True)
    except subprocess.CalledProcessError:
        print(f"⚠️ O download de {taxon} foi interrompido ou falhou. Rode o script novamente para retomar.")
        continue

    # PASSO 3: Validação e Contagem
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
print("🎉 DOWNLOADS DE FUNGOS PROCESSADOS!")
print("Próximo passo: rodar preparar_blast.py pra indexar, depois a curadoria")
print("de habitat (ver comentário no topo deste arquivo).")
print("=" * 60)
