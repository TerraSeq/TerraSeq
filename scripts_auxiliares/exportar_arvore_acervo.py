import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

# Exporta, para cada banco do acervo, quantos genomas o banco tem em cada nó
# da árvore -- é o denominador dos percentuais das árvores dos relatórios
# ("genomas capturados / genomas no banco" em cada táxon, grupo funcional,
# função ecológica e tamanho), pedido pelo orientador: percentuais sempre em
# relação ao total de genomas do banco, não aos acertos da análise.
#
# Gera docs/dados/arvore/<grupo>.json (um arquivo por banco, o relatório só
# baixa os bancos que a análise usou):
#   {"grupo": ..., "gerado_em": ..., "taxons": {nome: genomas},
#    "funcional": [[funcao, grande_grupo, tamanho, genomas], ...]}
# A classificação funcional vai como combinações (função, grupo, tamanho)
# porque o mesmo grande grupo pode cair em funções diferentes dependendo da
# linhagem -- o relatório soma as combinações que cada coluna precisa.
#
# Usa as mesmas fontes do resto do pipeline, pra os nomes baterem com os da
# árvore do relatório:
#   - organismos_por_grupo.csv (grupo, organismo, taxid, qtd_genomas), já sem
#     a curadoria de habitat (TAXIDS_EXCLUIDOS), como exportar_acervo_genomas.py;
#   - taxonomia_local.linhagem_por_taxid (mesma base de taxonomia do relatório);
#   - main.classificar_ecologia (mesma classificação funcional do relatório).
#
# Uso, no servidor, na raiz do projeto, no ambiente do main.py:
#   python3 scripts_auxiliares/exportar_arvore_acervo.py
#   git add docs/dados/arvore && git commit -m "Arvore do acervo" && git push

RAIZ_PROJETO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ_PROJETO, "src"))
os.environ.setdefault("TERRASEQ_SEM_PLANILHA", "1")

from curar_bancos import TAXIDS_EXCLUIDOS  # noqa: E402
from exportar_acervo_genomas import CAMINHO_CSV  # noqa: E402

DIRETORIO_SAIDA = os.path.join(RAIZ_PROJETO, "docs", "dados", "arvore")


def contar_por_grupo(linhas, linhagem_de, classificar):
    """linhas: dicts do CSV. Devolve {grupo: {"taxons": {...}, ...}}."""
    bancos = defaultdict(lambda: {"taxons": defaultdict(int), "funcional": defaultdict(int)})
    sem_linhagem = defaultdict(int)
    for linha in linhas:
        grupo, taxid = linha["grupo"], linha["taxid"]
        qtd = int(linha["qtd_genomas"] or 0)
        if not qtd or taxid in TAXIDS_EXCLUIDOS.get(grupo, {}):
            continue
        linhagem = list(linhagem_de(taxid) or [])
        # Igual ao relatório (main.construir_arvore_aninhada): sem "cellular organisms".
        if linhagem and linhagem[0].lower() == "cellular organisms":
            linhagem.pop(0)
        if not linhagem:
            sem_linhagem[grupo] += qtd
            continue
        b = bancos[grupo]
        for nome in dict.fromkeys(linhagem):        # cada nó conta o genoma uma vez
            b["taxons"][nome] += qtd
        grande_grupo, tamanho, funcao = classificar(linhagem)
        b["funcional"][(funcao, grande_grupo, tamanho)] += qtd
    return bancos, sem_linhagem


if __name__ == "__main__":
    if not os.path.exists(CAMINHO_CSV):
        print(f"❌ {CAMINHO_CSV} não existe. Rode scripts_auxiliares/listar_organismos_por_grupo.py primeiro.")
        sys.exit(1)

    import taxonomia_local  # noqa: E402
    from main import classificar_ecologia  # noqa: E402

    with open(CAMINHO_CSV, "r", encoding="utf-8", newline="") as f:
        linhas = list(csv.DictReader(f))

    print(f"Lendo {len(linhas)} organismos de {CAMINHO_CSV} ...")
    bancos, sem_linhagem = contar_por_grupo(linhas, taxonomia_local.linhagem_por_taxid, classificar_ecologia)

    os.makedirs(DIRETORIO_SAIDA, exist_ok=True)
    gerado_em = datetime.now().strftime("%Y-%m-%d %H:%M")
    for grupo, contagens in sorted(bancos.items()):
        saida = {"grupo": grupo, "gerado_em": gerado_em}
        saida["taxons"] = dict(sorted(contagens["taxons"].items()))
        saida["funcional"] = [[f, g, t, n] for (f, g, t), n in sorted(contagens["funcional"].items())]
        caminho = os.path.join(DIRETORIO_SAIDA, f"{grupo}.json")
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
        total = sum(contagens["funcional"].values())
        print(f"🌳 {grupo}: {total} genomas, {len(contagens['taxons'])} táxons -> {os.path.relpath(caminho, RAIZ_PROJETO)}")
    for grupo, qtd in sorted(sem_linhagem.items()):
        print(f"⚠️ {grupo}: {qtd} genoma(s) sem linhagem na base de taxonomia local (ficam fora da árvore)")

    print("\n✅ Pronto. Próximo passo: git add docs/dados/arvore && git commit && git push")
