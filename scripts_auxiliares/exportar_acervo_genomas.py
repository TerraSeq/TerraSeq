import os
import csv
import json
import sys
from datetime import datetime

# Exporta um JSON público (docs/dados/acervo_genomas.json) com a contagem de
# genomas e a lista de organismos distintos de cada banco JÁ CURADO --
# alimenta a seção "Acervo de Genomas" da página inicial (carrossel +
# busca por organismo).
#
# IMPORTANTE: organismos_por_grupo.csv (gerado por listar_organismos_por_
# grupo.py) lista TUDO que foi baixado do NCBI, sem descontar a curadoria
# de habitat (TAXIDS_EXCLUIDOS em curar_bancos.py) -- só data/blast_dbs/
# (o banco de fato pesquisado pelo BLAST) reflete a exclusão. Sem filtrar
# aqui, o site mostraria organismos marinhos/fora de escopo que já
# removemos da busca de verdade, o que seria cientificamente incorreto e
# contradiz todo o trabalho de curadoria feito. Este script importa
# TAXIDS_EXCLUIDOS/ACCESSIONS_EXCLUIDAS direto de curar_bancos.py (fonte
# única da verdade) em vez de manter uma segunda lista duplicada.

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from curar_bancos import TAXIDS_EXCLUIDOS  # noqa: E402

DIRETORIO_MANIFESTOS = "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/manifestos"
CAMINHO_CSV = os.path.join(DIRETORIO_MANIFESTOS, "organismos_por_grupo.csv")

RAIZ_PROJETO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DIRETORIO_SAIDA = os.path.join(RAIZ_PROJETO, "docs", "dados")
CAMINHO_SAIDA = os.path.join(DIRETORIO_SAIDA, "acervo_genomas.json")


def taxids_banidos_do_grupo(grupo):
    return set(TAXIDS_EXCLUIDOS.get(grupo, {}).keys())


if __name__ == "__main__":
    if not os.path.exists(CAMINHO_CSV):
        print(f"❌ {CAMINHO_CSV} não existe. Rode scripts_auxiliares/listar_organismos_por_grupo.py primeiro.")
        sys.exit(1)

    print("Exportando acervo de genomas (já descontando a curadoria de habitat)...\n")

    bancos = {}  # grupo -> {"organismos": [...], "genomas": 0}
    total_excluidos_organismos = 0
    total_excluidos_genomas = 0

    with open(CAMINHO_CSV, "r", encoding="utf-8", newline="") as f:
        leitor = csv.DictReader(f)
        for linha in leitor:
            grupo = linha["grupo"]
            organismo = linha["organismo"]
            taxid = linha["taxid"]
            qtd_genomas = int(linha["qtd_genomas"] or 0)

            if taxid in taxids_banidos_do_grupo(grupo):
                total_excluidos_organismos += 1
                total_excluidos_genomas += qtd_genomas
                continue

            if grupo not in bancos:
                bancos[grupo] = {"organismos": [], "genomas": 0}
            bancos[grupo]["organismos"].append(organismo)
            bancos[grupo]["genomas"] += qtd_genomas

    lista_bancos = []
    total_genomas = 0
    for grupo, dados in sorted(bancos.items()):
        dados["organismos"].sort()
        lista_bancos.append({
            "id": grupo,
            "nome": grupo.capitalize(),
            "genomas": dados["genomas"],
            "organismos": dados["organismos"],
        })
        total_genomas += dados["genomas"]
        print(f"🧬 {grupo}: {len(dados['organismos'])} organismo(s), {dados['genomas']} genoma(s) (pós-curadoria)")

    lista_bancos.sort(key=lambda b: -b["genomas"])

    saida = {
        "gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_bancos": len(lista_bancos),
        "total_genomas": total_genomas,
        "bancos": lista_bancos,
    }

    os.makedirs(DIRETORIO_SAIDA, exist_ok=True)
    with open(CAMINHO_SAIDA, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\n✅ Salvo em {CAMINHO_SAIDA}")
    print(f"   {len(lista_bancos)} bancos, {total_genomas} genomas no total")
    print(f"   Descontados por curadoria: {total_excluidos_organismos} organismo(s), {total_excluidos_genomas} genoma(s)")
    print("\nPróximo passo: 'git add docs/dados/acervo_genomas.json', commit e push -- a página inicial já vai buscar esse arquivo.")
