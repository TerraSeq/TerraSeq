"""
Vitrine do site: a lista de análises publicadas em docs/dados/vitrine.json.

A página inicial (docs/index.html) lê esse arquivo e monta a tabela
(docs/js/vitrine/tabela-resultados.js). O pipeline só acrescenta uma entrada
por análise publicada -- não escreve HTML.

Uso pelo pipeline (main.py e main_issues.py, dentro da trava "publicacao"):

    import vitrine
    vitrine.adicionar_analise(req, req_id, resultado_json)

Uso na linha de comando, na raiz do projeto:

    python3 src/vitrine.py listar
    python3 src/vitrine.py remover REQ-20261026-191323   # tira da vitrine (o relatório continua no ar)

Depois de remover, faça commit e push de docs/dados/vitrine.json.
"""
import json
import os
import sys
import tempfile
from datetime import datetime

RAIZ_PROJETO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CAMINHO_VITRINE = os.path.join(RAIZ_PROJETO, "docs", "dados", "vitrine.json")
# Caminho relativo à raiz do projeto, para o "git add" da publicação.
CAMINHO_VITRINE_GIT = "docs/dados/vitrine.json"

# Normaliza a capitalização do nome do banco exibido na tabela do site -- o
# requerente digita esse campo livremente (Google Forms/GitHub Issues), então
# "RefSeq"/"refseq" ou "Mistura_teste"/"mistura_teste" viravam entradas
# diferentes no filtro por banco da tabela. Bancos ainda não mapeados aqui
# continuam exibidos exatamente como o requerente digitou.
MAPA_BANCO_CANONICO = {
    "acari": "Acari",
    "banco_solo_unificado": "Banco_Solo_Unificado",
    "eucariotos": "eucariotos",
    "procariotos": "procariotos",
    "formigas": "Formigas",
    "fungi": "Fungi",
    "isoptera": "Isoptera",
    "minhocas": "Minhocas",
    "mistura_teste": "Mistura_teste",
    "protozoa": "Protozoa",
    "refseq": "RefSeq",
    "refseqsoil": "RefSeqSoil",
}


def montar_entrada(req, req_id, resultado_json=None, data=None):
    """Entrada da vitrine para uma análise.

    req: pedido já em português (as chaves 'Primer forward', 'Região alvo'...).
    resultado_json: o result.json da análise (nome do par e amplicon médio).
    data: datetime da publicação (padrão: agora).
    """
    resultado_json = resultado_json or {}
    alvo = str(req.get("Região alvo", "Não informada")).strip()
    banco_bruto = str(req.get("Banco de Dados", "Protozoa")).strip()
    nome_par = str(resultado_json.get("primers", {}).get("pair_name", "")).strip() or f"Par {alvo}"
    try:
        amplicon = int(round(float(resultado_json.get("summary", {}).get("mean_amplicon_size"))))
    except (TypeError, ValueError):
        amplicon = 0
    return {
        "id": req_id,
        "nome_par": nome_par,
        "alvo": alvo,
        "banco": MAPA_BANCO_CANONICO.get(banco_bruto.lower(), banco_bruto),
        "forward": str(req.get("Primer forward", "")).strip().upper(),
        "reverse": str(req.get("Primer reverse", "")).strip().upper(),
        "amplicon_bp": max(amplicon, 0),
        "data": (data or datetime.now()).strftime("%Y-%m-%d"),
    }


def ler_analises(caminho=CAMINHO_VITRINE):
    if not os.path.exists(caminho):
        return []
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f).get("analises", [])


def gravar_analises(analises, caminho=CAMINHO_VITRINE):
    """Grava num arquivo temporário e troca no fim: se o processo cair no meio,
    o vitrine.json antigo continua inteiro (nunca fica um JSON pela metade)."""
    pasta = os.path.dirname(caminho)
    os.makedirs(pasta, exist_ok=True)
    fd, temporario = tempfile.mkstemp(dir=pasta, prefix=".vitrine-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"analises": analises}, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(temporario, caminho)
    except BaseException:
        if os.path.exists(temporario):
            os.remove(temporario)
        raise


def adicionar_analise(req, req_id, resultado_json=None, caminho=CAMINHO_VITRINE):
    """Acrescenta a análise no fim da vitrine (ou substitui, se o mesmo ID já estiver lá)."""
    print(f"🖥️ Atualizando a vitrine ({os.path.relpath(caminho, RAIZ_PROJETO)})...")
    entrada = montar_entrada(req, req_id, resultado_json)
    analises = [a for a in ler_analises(caminho) if a.get("id") != req_id]
    analises.append(entrada)
    gravar_analises(analises, caminho)
    print(f"   ✅ Vitrine atualizada: {len(analises)} análise(s).")
    return entrada


def remover_analise(req_id, caminho=CAMINHO_VITRINE):
    """Tira a análise da vitrine. Devolve True se ela estava lá."""
    analises = ler_analises(caminho)
    restantes = [a for a in analises if a.get("id") != req_id]
    if len(restantes) == len(analises):
        return False
    gravar_analises(restantes, caminho)
    return True


if __name__ == "__main__":
    comando = sys.argv[1] if len(sys.argv) > 1 else ""
    if comando == "listar":
        for a in ler_analises():
            print(f"{a['id']}  {a['data']}  {a['banco']:<12} {a['nome_par']}")
    elif comando == "remover" and len(sys.argv) > 2:
        for req_id in sys.argv[2:]:
            print(f"{'🗑️ removida' if remover_analise(req_id) else '⚠️ não estava na vitrine'}: {req_id}")
        print("Agora: git add docs/dados/vitrine.json && git commit && git push")
    else:
        print(__doc__)
        sys.exit(1)
