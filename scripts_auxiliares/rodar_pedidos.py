#!/usr/bin/env python3
"""
Roda uma lista de pedidos um depois do outro, SEM passar pelo formulario nem
pelas Issues. Cada pedido faz o mesmo que o main.py faria: BLAST + relatorio,
linha na vitrine (docs/index.html), commit/push no GitHub e e-mail de
"relatorio pronto". Se um pedido falhar, segue para o proximo e mostra o
resumo no fim.

Edite a lista PEDIDOS logo abaixo (ja vem com o LR0R/LR7 em eucariotos, amplicon 1000-4000) e rode,
no servidor, na raiz do projeto, na branch main:

    nohup python3 scripts_auxiliares/rodar_pedidos.py > pedidos.log 2>&1 &
    tail -f pedidos.log        # acompanhar (Ctrl+C sai do tail, nao para o script)

Opcoes:
    --simular     mostra o que seria rodado e sai
    --sem-push    nao faz commit/push nem mexe na vitrine
    --sem-email   nao envia e-mail
    --so N        roda so o pedido de numero N da lista (1, 2, ...)

O banco "eucariotos" usa ate ~114 GB de RAM: nao deixe o main.py ou o
main_issues.py processando outra analise grande ao mesmo tempo (a fila
protege quando eles estao rodando, mas feche-os para nao disputar a vez).
"""
import argparse
import os
import sys
import time
import traceback
from datetime import datetime

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

NOME = "Tiago M Gabriel"
EMAIL = "tiago.gabriel@edu.ufes.br"   # recebe o aviso de cada relatorio

# Parametros-base (iguais aos dos pedidos anteriores); cada pedido pode sobrescrever.
BASE = {
    "Nome completo": NOME,
    "Email": EMAIL,
    "Região alvo": "18S-ITS-28S",
    "Tipo de organismo": "Eukaryota",
    "Banco de Dados": "eucariotos",
    "Tamanho do amplicon: MIN": 2000,
    "Tamanho do amplicon: MAX": 8000,
    "Máximo de Mismatches na extremidade 3": 3,
    "E-value máximo": 10.0,
    "Cobertura mínima": 70,
    "Limite de hits": 30000,
    "Temperatura de Melting mínima (Tm)": 0,
}

PEDIDOS = [
    # LR0R/LR7 (LSU) com limite de cima maior (4000): o relatorio com 1000-2500
    # tinha cauda ate 2500, entao pode haver amplicons mais longos descartados.
    dict(BASE, **{"Nome do Par de Primers": "LR0R/LR7",
                  "Região alvo": "LSU", "Tipo de organismo": "Eukaryota",
                  "Banco de Dados": "eucariotos",
                  "Tamanho do amplicon: MIN": 1000, "Tamanho do amplicon: MAX": 4000,
                  "Primer forward": "ACCCGCTGAACTTAAGC",
                  "Primer reverse": "TACTACCACCAAGATCT"}),
]


def novo_req_id():
    base = "REQ-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    sufixo, req_id = 1, base
    while os.path.exists(os.path.join(RAIZ, "docs", "reports", req_id)):
        sufixo += 1
        req_id = f"{base}-{sufixo}"
    return req_id


def main_cli():
    ap = argparse.ArgumentParser(description="Roda pedidos em sequencia, sem formulario.")
    ap.add_argument("--simular", action="store_true")
    ap.add_argument("--sem-push", action="store_true")
    ap.add_argument("--sem-email", action="store_true")
    ap.add_argument("--so", type=int, help="roda so o pedido N da lista")
    args = ap.parse_args()

    lista = list(enumerate(PEDIDOS, 1))
    if args.so:
        lista = [(n, p) for n, p in lista if n == args.so]
        if not lista:
            sys.exit(f"❌ Nao existe o pedido {args.so} (a lista tem {len(PEDIDOS)}).")

    if args.simular:
        for n, p in lista:
            print(f"\n[{n}] {p['Nome do Par de Primers']}  banco={p['Banco de Dados']}")
            print(f"    F: {p['Primer forward']}\n    R: {p['Primer reverse']}")
            print(f"    amplicon {p['Tamanho do amplicon: MIN']}-{p['Tamanho do amplicon: MAX']}, "
                  f"mismatches 3' <= {p['Máximo de Mismatches na extremidade 3']}, cobertura >= {p['Cobertura mínima']}%")
        return

    os.environ["TERRASEQ_SEM_PLANILHA"] = "1"
    sys.path.insert(0, os.path.join(RAIZ, "src"))
    import main  # noqa: E402
    import bloqueios  # noqa: E402

    resumo = []
    for ordem, (n, req) in enumerate(lista, 1):
        nome = req["Nome do Par de Primers"]
        print(f"\n{'=' * 70}\n[{ordem}/{len(lista)}] {nome}\n{'=' * 70}")
        req_id = novo_req_id()
        inicio = time.time()
        try:
            _, resultado = main.run_pipeline(req, req_id)
            if not args.sem_push:
                with bloqueios.bloqueio("publicacao", "⏳ Aguardando outra publicação terminar..."):
                    main.atualizar_vitrine_html(req, req_id, resultado)
                    main.publicar_no_github(req_id)
            if not args.sem_email and req.get("Email"):
                try:
                    main.enviar_email_notificacao(str(req["Email"]).strip(), req_id)
                except Exception as e:
                    print(f"   ⚠️ Relatório pronto, mas o e-mail falhou: {e}")
            s = resultado["summary"]
            minutos = (time.time() - inicio) / 60
            detalhe = (f"{s.get('unique_organisms')} genomas, cobertura {s.get('estimated_coverage')}, "
                       f"{minutos:.0f} min")
            print(f"   ✅ {detalhe}")
            resumo.append((nome, "ok", req_id, detalhe))
        except Exception as e:
            traceback.print_exc()
            print(f"   🔥 Falhou: {e}; seguindo para o próximo.")
            resumo.append((nome, "ERRO", req_id, str(e)[:100]))

    print(f"\n{'=' * 70}\nRESUMO\n{'=' * 70}")
    for nome, status, req_id, detalhe in resumo:
        print(f"{status:>5}  {req_id}  {nome}  {detalhe}")
    if any(s == "ERRO" for _, s, _, _ in resumo):
        sys.exit(1)


if __name__ == "__main__":
    main_cli()
