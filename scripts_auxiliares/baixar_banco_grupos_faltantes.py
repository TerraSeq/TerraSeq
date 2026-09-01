import subprocess
import os
import json
import zipfile

# Baixa de verdade (rehydrate) os 8 grupos de invertebrados que faltam pra
# cobrir o Atlas Global da Biodiversidade do Solo. Rode
# scripts_auxiliares/estimar_espaco_grupos_faltantes.py ANTES deste, pra
# conferir o tamanho estimado de cada grupo contra o espaço livre em disco
# (df -h) -- esse script aqui reaproveita os metadados que o estimador já
# baixou (pasta_taxon já existe -> pula a etapa de metadados), então rodar
# o estimador primeiro não duplica trabalho nenhum.
#
# Ver comentário completo sobre a escolha dos nomes/escopo em
# estimar_espaco_grupos_faltantes.py (mesmos 8 grupos, mesmos motivos).
#
# ATENCAO -- assim como fungos, NCBI Datasets não tem filtro por habitat (só
# por taxonomia), então isso vai trazer organismos NAO-solo também (ex:
# besouros aquáticos, abelhas exclusivamente urbanas/domesticadas, aranhas
# marinhas de zona entremarés, etc.) -- depois de baixar, repetir o mesmo
# processo de curadoria já usado nos outros grupos:
#   1. python3 scripts_auxiliares/gerar_manifesto_taxid.py
#   2. python3 scripts_auxiliares/listar_organismos_por_grupo.py
#   3. python3 scripts_auxiliares/detectar_habitat_suspeito.py
#   4. revisar e excluir via curar_bancos.py (TAXIDS_EXCLUIDOS)
#
# ATENCAO 2 -- Coleoptera é a maior e mais diversa ordem de organismos do
# planeta (370 mil+ espécies descritas); mesmo que a cobertura de genomas
# sequenciados seja bem menor que a diversidade real, pode ser o maior
# grupo desta leva. Confira o tamanho estimado antes de rodar.

GRUPOS_FALTANTES = [
    "coleoptera",
    "protura",
    "diplura",
    "pseudoscorpiones",
    "araneae",
    "scorpiones",
    "gastropoda",
    "apoidea",
]

DIRETORIO_DESTINO = "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/refseq"
os.makedirs(DIRETORIO_DESTINO, exist_ok=True)

print("🚀 Iniciando download ROBUSTO (Retomável) dos grupos de invertebrados faltantes...\n")
print(f"📂 Destino: {DIRETORIO_DESTINO}\n")

for taxon in GRUPOS_FALTANTES:
    pasta_taxon = os.path.join(DIRETORIO_DESTINO, taxon)
    arquivo_zip = os.path.join(DIRETORIO_DESTINO, f"{taxon}.zip")

    print("-" * 60)
    print(f"📥 Processando {taxon.upper()}...")

    # PASSO 1: Baixar o pacote "desidratado" (pula se o estimador já baixou)
    if not os.path.exists(pasta_taxon):
        comando_zip = [
            "datasets", "download", "genome", "taxon", taxon,
            "--assembly-source", "all",
            "--reference",
            "--dehydrated",
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
    else:
        print("   -> Metadados já existem (do estimador ou de uma tentativa anterior).")

    # PASSO 2: Reidratar (Baixar os arquivos pesados de fato). Retomável.
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
print("🎉 DOWNLOADS DOS GRUPOS FALTANTES PROCESSADOS!")
print("Próximo passo: rodar preparar_blast.py pra indexar, depois a curadoria")
print("de habitat (ver comentário no topo deste arquivo).")
print("=" * 60)
