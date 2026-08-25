import os
import glob
import json

DIRETORIO_ORIGEM = "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/refseq"
DIRETORIO_MANIFESTOS = "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/manifestos"

# Gera, pra cada grupo baixado, um manifesto TSV (accession_sequencia -> taxId
# -> nome_organismo -> descricao) 100% local, sem consultar o NCBI pela rede.
#
# O NCBI Datasets ja salva, junto de cada genoma baixado, um
# assembly_data_report.jsonl com o taxId do organismo (nivel GENOMA). Cada
# genoma tem varias sequencias/scaffolds dentro dele (nivel SEQUENCIA, que e
# o que aparece como "sseqid" nos hits do BLAST) -- entao cruzamos os dois:
# lemos o taxId de cada genoma (pasta ncbi_dataset/data/<accession_genoma>/)
# e aplicamos esse mesmo taxId a todas as sequencias dentro da pasta dele.
#
# Esse manifesto e consumido por src/taxonomia_local.py pra montar a arvore
# taxonomica do relatorio sem precisar de internet.


def _carregar_taxid_por_genoma(pasta_taxon):
    caminho_relatorio = os.path.join(pasta_taxon, "ncbi_dataset", "data", "assembly_data_report.jsonl")
    mapa = {}
    if not os.path.exists(caminho_relatorio):
        return mapa
    with open(caminho_relatorio, "r", encoding="utf-8", errors="ignore") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            dados = json.loads(linha)
            acc_genoma = dados.get("accession", "")
            organismo = dados.get("organism", {})
            taxid = organismo.get("taxId")
            nome = organismo.get("organismName", "")
            if acc_genoma and taxid:
                mapa[acc_genoma] = (str(taxid), nome)
    return mapa


def gerar_manifesto_taxid(taxon):
    pasta_taxon = os.path.join(DIRETORIO_ORIGEM, taxon)
    taxid_por_genoma = _carregar_taxid_por_genoma(pasta_taxon)
    if not taxid_por_genoma:
        print(f"  ⚠️ Nenhum assembly_data_report.jsonl encontrado/válido para {taxon}, pulando.")
        return

    os.makedirs(DIRETORIO_MANIFESTOS, exist_ok=True)
    caminho_saida = os.path.join(DIRETORIO_MANIFESTOS, f"{taxon}_taxid.tsv")
    pasta_dados = os.path.join(pasta_taxon, "ncbi_dataset", "data")
    total_sequencias = 0

    with open(caminho_saida, "w", encoding="utf-8") as out:
        for acc_genoma, (taxid, nome_organismo) in taxid_por_genoma.items():
            pasta_genoma = os.path.join(pasta_dados, acc_genoma)
            arquivos_fna = glob.glob(os.path.join(pasta_genoma, "*.fna"))
            for fna in arquivos_fna:
                with open(fna, "r", errors="ignore") as f:
                    for linha in f:
                        if linha.startswith(">"):
                            resto = linha[1:].strip()
                            # Mesma normalizacao que main.py usa antes de
                            # consultar (remove a versao ".1" do accession),
                            # pra bater exatamente com a chave de busca.
                            acc_sequencia = resto.split(" ")[0].split(".")[0]
                            descricao = resto
                            out.write(f"{acc_sequencia}\t{taxid}\t{nome_organismo}\t{descricao}\n")
                            total_sequencias += 1

    print(f"  -> {taxon}: {total_sequencias} sequência(s) mapeada(s) em {caminho_saida}")


if __name__ == "__main__":
    print("Gerando manifestos de taxId (accession -> taxId -> organismo), 100% local.\n")
    grupos = [f.name for f in os.scandir(DIRETORIO_ORIGEM) if f.is_dir()]
    for taxon in grupos:
        print(f"🧬 {taxon}")
        gerar_manifesto_taxid(taxon)
    print("\n✅ Manifestos gerados. A etapa de classificação taxonômica no main.py agora roda 100% local")
    print("   (sem consultar o NCBI pela rede), exceto pra sequências que não estejam mapeadas aqui.")
