#!/usr/bin/env python3
"""
Reprocessa relatórios já existentes (docs/reports/<REQ-ID>/) com o pipeline
atual, um depois do outro, sem precisar da planilha do Google.

Como funciona: os parâmetros de cada pedido (primers, banco, tamanho do
amplicon, mismatches, e-value, cobertura mínima, Tm, limite de hits, nome,
e-mail...) estão guardados no result.json do próprio relatório. O script
reconstrói o "req" original a partir dele e chama o mesmo run_pipeline do
main.py, sobrescrevendo a pasta do relatório (result.json, index.html,
primer.fasta, sequencias_completas.json). Depois commita e dá push de cada
relatório assim que ele termina, então o que já acabou não se perde se algo
falhar no meio.

Preserva: o REQ-ID, a data de submissão original, o nome e o e-mail de quem
pediu. NÃO mexe: a linha do relatório na vitrine (docs/index.html), a
planilha e o envio de e-mail (nada disso é refeito).

Uso (no servidor, na raiz do projeto, com o mesmo ambiente do main.py):

    # ver o que seria reprocessado, sem rodar BLAST nem importar o main.py
    python3 scripts_auxiliares/reprocessar_relatorios.py --simular

    # rodar os 11 relatórios da lista padrão, em sequência
    nohup python3 scripts_auxiliares/reprocessar_relatorios.py > reprocessar.log 2>&1 &

    # só alguns, ou sem dar push
    python3 scripts_auxiliares/reprocessar_relatorios.py --ids REQ-20260922-0082 REQ-20260922-0085
    python3 scripts_auxiliares/reprocessar_relatorios.py --sem-push

É retomável: relatórios que já foram reprocessados (campo "reprocessed_at" no
result.json) são pulados, a menos que use --forcar. Se der erro em um, ele
segue pro próximo e mostra o resumo no fim.

ATENÇÃO: o BLAST do banco "eucariotos" chega a ~114GB de RAM. Não rode ao
mesmo tempo que o main.py estiver processando uma submissão nova.
"""
import argparse
import json
import os
import sys
import traceback
from datetime import datetime

RAIZ_PROJETO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PASTA_RELATORIOS = os.path.join(RAIZ_PROJETO, "docs", "reports")

# Ordem em que serão reprocessados.
RELATORIOS_PADRAO = [
    "REQ-20260922-0085",  # V4_Hugerth_F/D11_3143R
    "REQ-20260921-0079",  # V4_Brate_F/D9_2741R
    "REQ-20260921-0076",  # V4_Brate_F/D9_2593R
    "REQ-20260922-0082",  # V4_Brate_F/D11_3143R
    "REQ-20260922-0083",  # V4_Brate_F/22R
    "REQ-20260921-0072",  # V4_Balzano_F/D9_2742R
    "REQ-20260921-0075",  # V4_Balzano_F/D9_2593R
    "REQ-20260922-0087",  # V4_Balzano_F/D11_3143R
    "REQ-20260921-0078",  # V4_Balzano_F/22R
    "REQ-20260921-0073",  # V4_Balzano_F/21R
    "REQ-20260921-0081",  # 3NDf/21R
]


def caminho_result(req_id):
    return os.path.join(PASTA_RELATORIOS, req_id, "result.json")


def carregar_result(req_id):
    with open(caminho_result(req_id), "r", encoding="utf-8") as f:
        return json.load(f)


def reconstruir_req(antigo):
    """Reconstrói o dict 'req' (colunas da planilha) a partir do result.json."""
    m = antigo["metadata"]
    p = antigo["primers"]
    return {
        "Nome completo": m.get("submitted_by", "Pesquisador"),
        "Email": m.get("email", ""),
        "Primer forward": p["forward"],
        "Primer reverse": p["reverse"],
        "Nome do Par de Primers": p.get("pair_name", ""),
        "Região alvo": m.get("target_region", "Não informada"),
        "Tipo de organismo": m.get("organism", "Não informado"),
        "Banco de Dados": m.get("database", "refseqsoil"),
        "Tamanho do amplicon: MIN": m.get("amplicon_min", 20),
        "Tamanho do amplicon: MAX": m.get("amplicon_max", 9999),
        "Máximo de Mismatches na extremidade 3": m.get("max_mismatches", 0),
        "E-value máximo": m.get("e_value", 10.0),
        "Cobertura mínima": m.get("min_coverage", 0),
        "Limite de hits": m.get("max_hits", 30000),
        "Temperatura de Melting mínima (Tm)": m.get("min_tm", 0),
    }


def reprocessar(req_id, main):
    antigo = carregar_result(req_id)
    req = reconstruir_req(antigo)

    # run_pipeline só escreve sequencias_completas.json quando há sequências
    # fora do orçamento; remove o antigo pra não sobrar um arquivo defasado.
    caminho_seqs = os.path.join(PASTA_RELATORIOS, req_id, "sequencias_completas.json")
    if os.path.exists(caminho_seqs):
        os.remove(caminho_seqs)

    _, novo = main.run_pipeline(req, req_id)

    # run_pipeline grava "agora" como data de submissão; devolve a original.
    novo["metadata"]["submitted_at"] = antigo["metadata"].get("submitted_at", novo["metadata"]["submitted_at"])
    novo["reprocessed_at"] = datetime.now().strftime("%d/%m/%Y às %H:%M")
    with open(caminho_result(req_id), "w", encoding="utf-8") as f:
        json.dump(novo, f, ensure_ascii=False, separators=(",", ":"))

    return antigo["summary"], novo["summary"]


def main_cli():
    ap = argparse.ArgumentParser(description="Reprocessa relatórios existentes com o pipeline atual.")
    ap.add_argument("--ids", nargs="+", help="REQ-IDs a reprocessar (padrão: a lista RELATORIOS_PADRAO do script)")
    ap.add_argument("--forcar", action="store_true", help="reprocessa mesmo os que já têm 'reprocessed_at'")
    ap.add_argument("--sem-push", action="store_true", help="não commita nem dá push a cada relatório")
    ap.add_argument("--simular", action="store_true", help="só mostra os parâmetros reconstruídos; não roda nada")
    args = ap.parse_args()

    ids = args.ids or RELATORIOS_PADRAO

    # Valida tudo antes de começar, pra não descobrir no relatório 8 que faltava um.
    faltando = [i for i in ids if not os.path.exists(caminho_result(i))]
    if faltando:
        print(f"❌ Sem result.json em docs/reports/ para: {', '.join(faltando)}")
        sys.exit(1)

    if args.simular:
        for req_id in ids:
            antigo = carregar_result(req_id)
            req = reconstruir_req(antigo)
            ja = "  (já reprocessado)" if "reprocessed_at" in antigo else ""
            print(f"\n{req_id}{ja}")
            for k, v in req.items():
                if k not in ("Email",):
                    print(f"   {k}: {v}")
            print(f"   [antes] genomas únicos={antigo['summary'].get('unique_organisms')} "
                  f"cobertura={antigo['summary'].get('estimated_coverage')}")
        return

    # Importa o main.py sem conectar na planilha nem iniciar o monitoramento.
    os.environ["TERRASEQ_SEM_PLANILHA"] = "1"
    sys.path.insert(0, os.path.join(RAIZ_PROJETO, "src"))
    import main  # noqa: E402

    resumo = []
    for n, req_id in enumerate(ids, 1):
        print(f"\n{'=' * 70}\n[{n}/{len(ids)}] {req_id}\n{'=' * 70}")
        antigo = carregar_result(req_id)
        if "reprocessed_at" in antigo and not args.forcar:
            print(f"   ⏭️  já reprocessado em {antigo['reprocessed_at']} (use --forcar para refazer)")
            resumo.append((req_id, "pulado", ""))
            continue
        try:
            antes, depois = reprocessar(req_id, main)
            detalhe = (f"genomas únicos {antes.get('unique_organisms')} -> {depois.get('unique_organisms')}, "
                       f"cobertura {antes.get('estimated_coverage')} -> {depois.get('estimated_coverage')}")
            print(f"   ✅ {detalhe}")
            if not args.sem_push:
                main.publicar_no_github(req_id)
            resumo.append((req_id, "ok", detalhe))
        except Exception:
            traceback.print_exc()
            print(f"   🔥 Falhou em {req_id}; seguindo para o próximo.")
            resumo.append((req_id, "ERRO", ""))

    print(f"\n{'=' * 70}\nRESUMO\n{'=' * 70}")
    for req_id, status, detalhe in resumo:
        print(f"{status:>7}  {req_id}  {detalhe}")
    if any(s == "ERRO" for _, s, _ in resumo):
        sys.exit(1)


if __name__ == "__main__":
    main_cli()
