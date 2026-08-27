import os
import json
import csv
from collections import defaultdict

DIRETORIO_ORIGEM = "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/refseq"
DIRETORIO_MANIFESTOS = "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/manifestos"
CAMINHO_SAIDA = os.path.join(DIRETORIO_MANIFESTOS, "organismos_por_grupo.csv")

# Gera uma planilha (CSV) com TODOS os organismos distintos baixados em cada
# grupo, para revisão manual de curadoria -- confirmar se cada espécie
# realmente se encaixa no escopo de "organismo de solo" -- e para servir
# como contagem oficial de quantas espécies distintas existem por grupo
# (diferente da contagem de GENOMAS: uma mesma espécie pode ter várias
# cepas/isolados sequenciados, cada um virando um genoma separado).
#
# Lê direto dos assembly_data_report.jsonl (1 linha por genoma baixado, já
# com o nome do organismo), sem precisar abrir nenhum .fna -- muito mais
# rápido que gerar_manifesto_taxid.py.


def listar_organismos(taxon):
    caminho_relatorio = os.path.join(DIRETORIO_ORIGEM, taxon, "ncbi_dataset", "data", "assembly_data_report.jsonl")
    contagem = defaultdict(lambda: [0, ""])  # organismo -> [qtd_genomas, taxid]
    if not os.path.exists(caminho_relatorio):
        return contagem
    with open(caminho_relatorio, "r", encoding="utf-8", errors="ignore") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            dados = json.loads(linha)
            organismo = dados.get("organism", {})
            nome = organismo.get("organismName", "Desconhecido")
            taxid = organismo.get("taxId", "")
            contagem[nome][0] += 1
            contagem[nome][1] = taxid
    return contagem


if __name__ == "__main__":
    print("Levantando organismos distintos por grupo (a partir dos assembly_data_report.jsonl)...\n")
    os.makedirs(DIRETORIO_MANIFESTOS, exist_ok=True)
    grupos = sorted(f.name for f in os.scandir(DIRETORIO_ORIGEM) if f.is_dir())

    with open(CAMINHO_SAIDA, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["grupo", "organismo", "taxid", "qtd_genomas"])
        total_organismos_distintos = 0
        total_genomas = 0
        for taxon in grupos:
            contagem = listar_organismos(taxon)
            qtd_genomas_grupo = sum(qtd for qtd, _ in contagem.values())
            print(f"🧬 {taxon}: {len(contagem)} organismo(s) distinto(s) em {qtd_genomas_grupo} genoma(s)")
            total_organismos_distintos += len(contagem)
            total_genomas += qtd_genomas_grupo
            for nome, (qtd, taxid) in sorted(contagem.items(), key=lambda item: -item[1][0]):
                writer.writerow([taxon, nome, taxid, qtd])

    print(f"\n✅ Planilha salva em {CAMINHO_SAIDA}")
    print(f"   Organismos DISTINTOS (todas as espécies, todos os grupos): {total_organismos_distintos}")
    print(f"   Genomas no total (várias cepas/isolados por espécie contam separado): {total_genomas}")
    print("\n   Abre o CSV no Excel/Sheets: colunas grupo/organismo/taxid/qtd_genomas,")
    print("   já ordenado por grupo e por quantidade de genomas (maior primeiro).")
