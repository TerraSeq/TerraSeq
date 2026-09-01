import subprocess
import os
import json
import zipfile

# Os 8 grupos de invertebrados que faltam pra cobrir o Atlas Global da
# Biodiversidade do Solo (Cap. II - Diversidade), decididos após comparar o
# capítulo inteiro com os 24 grupos já curados. Ficaram DE FORA por decisão
# explícita (não é esquecimento):
#   - Megafauna (Mammalia/Reptilia/Amphibia): foge do escopo do projeto
#     (vertebrados grandes, fáceis de identificar sem eDNA) e genomas de
#     mamífero facilmente passam de 2-3GB cada, contra poucos MB de um
#     genoma bacteriano -- pesaria muito no disco pra pouco benefício.
#   - Plantas (Viridiplantae/raízes): adiado, decisão de escopo separada.
#
# Nomes usam a taxonomia ACEITA pelo NCBI (não sempre igual ao nome usado no
# Atlas) e foram escolhidos pra NÃO sobrepor com grupos que já temos:
#   - "Arachnida" completo incluiria Acari (já temos) e Pseudoscorpiones de
#     novo -- por isso Araneae (aranhas) e Scorpiones (escorpiões) entram
#     separados, sem repetir o que já foi baixado.
#   - "Hymenoptera" completo incluiria Formicidae (já temos, formigas) de
#     novo -- por isso usamos só "Apoidea" (abelhas), que é uma superfamília
#     irmã de Formicoidea dentro de Hymenoptera, sem sobreposição.
GRUPOS_FALTANTES = {
    "coleoptera": "besouros -- Atlas chama de 'maior e mais diversa ordem de organismos do planeta' (370 mil+ espécies descritas). Pode ser um grupo GRANDE.",
    "protura": "hexápodes primitivos sem antenas/olhos, classe própria distinta de Collembola",
    "diplura": "hexápodes sem olhos com cercos, classe própria distinta de Collembola",
    "pseudoscorpiones": "'falsos escorpiões' -- aracnídeos sem ferrão, ordem própria (nome NCBI: Pseudoscorpiones, não Pseudoscorpionida)",
    "araneae": "aranhas -- aracnídeos, não sobrepõe com acari (ácaros) já baixado",
    "scorpiones": "escorpiões -- aracnídeos, não sobrepõe com acari já baixado",
    "gastropoda": "caracóis e lesmas de solo",
    "apoidea": "abelhas (inclui as escavadoras/solitárias que nidificam no solo) -- não sobrepõe com formicidae (formigas) já baixado",
}

DIRETORIO_DESTINO = "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/refseq"
os.makedirs(DIRETORIO_DESTINO, exist_ok=True)

print("🔍 ESTIMATIVA DE ESPAÇO -- só baixa metadados (leve), NÃO baixa sequências ainda.\n")
print(f"📂 Destino final (quando for baixar de verdade): {DIRETORIO_DESTINO}\n")

resumo = []

for taxon, descricao in GRUPOS_FALTANTES.items():
    pasta_taxon = os.path.join(DIRETORIO_DESTINO, taxon)
    arquivo_zip = os.path.join(DIRETORIO_DESTINO, f"{taxon}.zip")

    print("-" * 60)
    print(f"📥 {taxon.upper()} ({descricao})")

    if not os.path.exists(pasta_taxon):
        comando_zip = [
            "datasets", "download", "genome", "taxon", taxon,
            "--assembly-source", "all",
            "--reference",
            "--dehydrated",  # só metadados nesta etapa -- não baixa as sequências
            "--filename", arquivo_zip
        ]
        try:
            print("   -> Obtendo metadados do NCBI...")
            subprocess.run(comando_zip, check=True, capture_output=True)
            with zipfile.ZipFile(arquivo_zip, 'r') as zip_ref:
                zip_ref.extractall(pasta_taxon)
            os.remove(arquivo_zip)
        except subprocess.CalledProcessError as e:
            print(f"   ❌ Erro ao obter metadados de {taxon}: {e}")
            resumo.append((taxon, 0, 0, "erro"))
            continue
    else:
        print("   -> Metadados já baixados antes, reaproveitando.")

    relatorio_jsonl = os.path.join(pasta_taxon, "ncbi_dataset", "data", "assembly_data_report.jsonl")
    qtd_genomas = 0
    tamanho_total_bytes = 0

    if os.path.exists(relatorio_jsonl):
        with open(relatorio_jsonl, "r", encoding="utf-8", errors="ignore") as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                dados = json.loads(linha)
                tamanho = dados.get("assemblyStats", {}).get("totalSequenceLength")
                if tamanho:
                    tamanho_total_bytes += int(tamanho)
                    qtd_genomas += 1
        tamanho_gb = tamanho_total_bytes / (1024 ** 3)
        print(f"   ✅ {qtd_genomas} genoma(s) encontrado(s) -- ~{tamanho_gb:.2f} GB de sequência (estimativa)")
        resumo.append((taxon, qtd_genomas, tamanho_gb, "ok"))
    else:
        print("   ⚠️ Não foi possível ler o relatório desse grupo (pode não ter genoma nenhum no NCBI).")
        resumo.append((taxon, 0, 0, "sem relatorio"))

print("\n" + "=" * 60)
print("📊 RESUMO -- espaço estimado por grupo (antes de baixar de verdade)")
print("=" * 60)
total_geral_gb = 0
for taxon, qtd, tamanho_gb, status in resumo:
    total_geral_gb += tamanho_gb
    print(f"   {taxon:<16} {qtd:>6} genomas   ~{tamanho_gb:>8.2f} GB   [{status}]")
print("-" * 60)
print(f"   {'TOTAL':<16} {'':>6}              ~{total_geral_gb:>8.2f} GB")
print("=" * 60)
print("\nCompare esse total com o espaço livre (rode 'df -h' no disco onde fica data/refseq).")
print("Se der certo, roda scripts_auxiliares/baixar_banco_grupos_faltantes.py pra baixar de verdade")
print("(ele reaproveita esses metadados já baixados aqui, só falta a etapa de rehydrate).")
