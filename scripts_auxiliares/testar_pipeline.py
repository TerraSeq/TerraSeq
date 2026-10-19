#!/usr/bin/env python3
"""
Teste de ponta a ponta do pipeline, por cada um dos dois caminhos de entrada,
SEM mexer em nada de produção: não toca na planilha, nas Issues, na vitrine
(docs/index.html), não faz commit/push e só manda e-mail se você pedir.

    python3 scripts_auxiliares/testar_pipeline.py formulario        # caminho do main.py
    python3 scripts_auxiliares/testar_pipeline.py issue             # caminho do main_issues.py

O que ele faz:
  1. monta um pedido de teste (para "issue", gera o corpo da Issue a partir do
     próprio .github/ISSUE_TEMPLATE/solicitacao_analise.yml e passa pelo
     parse_issue_body -- assim pega divergência entre o formulário e o parser);
  2. roda o run_pipeline de verdade (BLAST + relatório) num banco pequeno;
  3. confere o resultado (primers certos, genomas únicos = soma por espécie,
     cobertura = genomas / banco, index.html = template atual, seletor EN|PT);
  4. apaga a pasta docs/reports/TESTE-... (use --manter para ficar com ela).

Opções:
  --so-parser     só confere formulário -> parser, sem rodar BLAST (leva 1 segundo)
  --banco NOME    banco do teste (padrão: formigas, ~212 genomas; ex: tardigrada, acari)
  --fwd/--rev     primers (padrão: V4_Balzano_F / D9_2593R)
  --email EMAIL   também testa o envio do e-mail de "relatório pronto" para você
  --manter        não apaga docs/reports/TESTE-...

Rode na raiz do projeto, no mesmo ambiente do main.py. Não rode junto com uma
análise grande (o BLAST de bancos grandes usa muita RAM).
"""
import argparse
import os
import re
import shutil
import sys
import time
import json
import traceback

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
YML_ISSUE = os.path.join(RAIZ, ".github", "ISSUE_TEMPLATE", "solicitacao_analise.yml")

FWD_PADRAO = "CCAGCASCYGCGGTAATTCC"   # V4_Balzano_F
REV_PADRAO = "GAGAGTCATAGTTACBYC"     # D9_2593R


def ok(msg):
    print(f"   ✅ {msg}")


def falha(msg):
    print(f"   ❌ {msg}")
    return 1


# --------------------------------------------------------------------------- pedidos
def pedido_formulario(args):
    """Mesmas colunas da planilha que o main.py lê (req.get(...))."""
    return {
        "Nome completo": "Teste Automatizado",
        "Email": args.email or "",
        "Primer forward": args.fwd,
        "Primer reverse": args.rev,
        "Nome do Par de Primers": "TESTE_V4_Balzano_F/D9_2593R",
        "Região alvo": "18S-ITS-28S",
        "Tipo de organismo": "Eukaryota",
        "Banco de Dados": args.banco,
        "Tamanho do amplicon: MIN": 2000,
        "Tamanho do amplicon: MAX": 8000,
        "Máximo de Mismatches na extremidade 3": 3,
        "E-value máximo": 10.0,
        "Cobertura mínima": 70,
        "Limite de hits": 30000,
        "Temperatura de Melting mínima (Tm)": 0,
    }


def campos_do_formulario_issue():
    """[(id, rótulo)] lidos do .yml do formulário da Issue (sem depender de PyYAML)."""
    texto = open(YML_ISSUE, encoding="utf-8").read()
    pares = re.findall(r"id:\s*(\w+)\s*\n\s*attributes:\s*\n\s*label:\s*(.+)", texto)
    return [(i, r.strip().strip('"').strip("'")) for i, r in pares]


def opcoes_dropdown(id_campo):
    """Opções de um menu do formulário da Issue, lidas do .yml."""
    texto = open(YML_ISSUE, encoding="utf-8").read()
    i = texto.index(f"id: {id_campo}")
    bloco = texto[i:texto.index("validations:", i)]
    return re.findall(r'^\s*-\s*"([^"]+)"', bloco, re.M)


def sem_descricao(valor):
    """Mesma regra do parse_issue_body: tira a descrição entre parênteses."""
    return re.sub(r"\s*\(.*\)\s*$", "", valor).strip()


def corpo_da_issue(args):
    """Corpo no formato que o GitHub gera para um formulário de Issue."""
    valores = {
        "nome": "Teste Automatizado",
        "email": args.email or "teste@example.com",
        "primer_pair_name": "TESTE_V4_Balzano_F/D9_2593R",
        "primer_fwd": args.fwd,
        "primer_rev": args.rev,
        "regiao_alvo": "18S-ITS-28S",
        # a opção completa do menu (com a descrição), como o GitHub entrega
        "banco_dados": next((o for o in opcoes_dropdown("banco_dados") if sem_descricao(o).lower() == args.banco.lower()), args.banco.capitalize()),
        "tipo_organismo": "Eukaryota",
        "max_mismatches": "3",
        "amp_min": "2000",
        "amp_max": "8000",
        "tm_min": "0",
        "evalue": "10",
        "cobertura": "70",
        "max_hits": "30000",
    }
    campos = campos_do_formulario_issue()
    faltando = [i for i, _ in campos if i not in valores]
    if faltando:
        print(f"   ⚠️ campos do formulário sem valor de teste (vão como '_No response_'): {faltando}")
    return "\n\n".join(f"### {rotulo}\n\n{valores.get(i, '_No response_')}" for i, rotulo in campos), valores


# --------------------------------------------------------------------------- conferências
def conferir_parser(m, args):
    """Formulário da Issue -> parse_issue_body: nenhum campo pode se perder."""
    print("\n🔎 Conferindo formulário da Issue → parse_issue_body ...")
    corpo, valores = corpo_da_issue(args)
    req = m.parse_issue_body(corpo)
    erros = 0
    esperado = {
        "Primer forward": args.fwd,
        "Primer reverse": args.rev,
        "Nome do Par de Primers": valores["primer_pair_name"],
        "Região alvo": valores["regiao_alvo"],
        "Banco de Dados": sem_descricao(valores["banco_dados"]),
        "Tipo de organismo": valores["tipo_organismo"],
        "Máximo de Mismatches na extremidade 3": valores["max_mismatches"],
        "Tamanho do amplicon: MIN": valores["amp_min"],
        "Tamanho do amplicon: MAX": valores["amp_max"],
        "Temperatura de Melting mínima (Tm)": valores["tm_min"],
        "E-value máximo": valores["evalue"],
        "Cobertura mínima": valores["cobertura"],
        "Limite de hits": valores["max_hits"],
        "Email": valores["email"],
        "Nome completo": valores["nome"],
    }
    for chave, valor in esperado.items():
        if str(req.get(chave, "")) == str(valor):
            ok(f"{chave}: {valor}")
        else:
            erros += falha(f"{chave}: esperado {valor!r}, o parser entregou {req.get(chave)!r}")
    return req, erros


def conferir_opcoes_do_formulario(m):
    """Toda opção dos menus do formulário precisa virar um banco/tipo válido no código."""
    print("\n🔎 Conferindo as opções dos menus do formulário × código ...")
    erros = 0
    fonte = open(os.path.join(RAIZ, "src", "main_issues.py"), encoding="utf-8").read()
    bloco = fonte[fonte.index("BANCOS_DISPONIVEIS = {"):fonte.index("BANCOS_GRUPOS = {")]
    chaves = set(re.findall(r'^\s*"(\w+)":\s*\(', bloco, re.M))
    oferecidos = set()
    for opcao in opcoes_dropdown("banco_dados"):
        req = m.parse_issue_body(f"### Banco de Dados\n\n{opcao}")
        nome = req["Banco de Dados"].lower()
        oferecidos.add(nome)
        if nome not in chaves:
            erros += falha(f"banco '{opcao}' do formulário não existe no código (cairia no refseqsoil sem avisar)")
    if not erros:
        ok(f"as {len(oferecidos)} opções de banco do formulário existem no código")
    fora = sorted(chaves - oferecidos - {"isoptera"})  # isoptera = alias de cupins
    if fora:
        print(f"   ℹ️ bancos do código que o formulário não oferece: {fora}")
    for opcao in opcoes_dropdown("tipo_organismo"):
        req = m.parse_issue_body(f"### Tipo de organismo\n\n{opcao}")
        if not req["Tipo de organismo"]:
            erros += falha(f"tipo de organismo '{opcao}' virou vazio")
    ok("tipos de organismo: " + ", ".join(sem_descricao(o) for o in opcoes_dropdown("tipo_organismo")))
    return erros


def conferir_resultado(req_id, req, pasta):
    print("\n🔎 Conferindo o relatório gerado ...")
    erros = 0
    caminho = os.path.join(pasta, "result.json")
    if not os.path.exists(caminho):
        return falha("result.json não foi gerado")
    r = json.load(open(caminho, encoding="utf-8"))
    s, m = r["summary"], r["metadata"]

    if r["primers"]["forward"] == str(req["Primer forward"]).strip().upper() and \
       r["primers"]["reverse"] == str(req["Primer reverse"]).strip().upper():
        ok("primers do relatório = primers do pedido")
    else:
        erros += falha(f"primers diferentes do pedido: {r['primers']}")

    ok(f"banco: {m.get('database')} | genomas no banco: {s['total_sequences_checked']} | hits: {s['total_matches']}")
    if s["total_sequences_checked"] <= 0:
        erros += falha("total_sequences_checked <= 0 (banco não mapeado?)")

    leaf = r.get("leaf_metadata", {})
    if s["total_matches"] == 0:
        print("   ⚠️ nenhum hit neste banco com esses primers -- o pipeline rodou, mas não há o que conferir")
        print("      (tente outro banco, ex: --banco acari)")
    else:
        soma = sum(v.get("genomas_capturados", 0) for v in leaf.values())
        if all("genomas_capturados" in v for v in leaf.values()):
            ok(f"cada espécie tem genomas_capturados ({len(leaf)} espécies)")
        else:
            erros += falha("há espécies sem genomas_capturados")
        if soma == s["unique_organisms"]:
            ok(f"genomas únicos do topo ({s['unique_organisms']}) = soma por espécie ({soma})")
        else:
            erros += falha(f"genomas únicos do topo ({s['unique_organisms']}) != soma por espécie ({soma})")
        cob = s["unique_organisms"] / s["total_sequences_checked"]
        if abs(cob - s["estimated_coverage"]) < 0.0001:
            ok(f"cobertura {s['estimated_coverage'] * 100:.1f}% = {s['unique_organisms']} / {s['total_sequences_checked']}")
        else:
            erros += falha(f"cobertura {s['estimated_coverage']} != {cob:.5f}")
        if s["unique_organisms"] > s["total_sequences_checked"]:
            erros += falha("mais genomas capturados do que genomas no banco")

    html = os.path.join(pasta, "index.html")
    template = os.path.join(RAIZ, "docs", "template.html")
    if os.path.exists(html) and open(html, "rb").read() == open(template, "rb").read():
        ok("index.html = docs/template.html atual")
    else:
        erros += falha("index.html ausente ou diferente do template atual")
    if b"data-lang-btn" in open(template, "rb").read():
        ok("template com seletor EN | PT")
    else:
        erros += falha("template sem o seletor de idioma")
    return erros


# --------------------------------------------------------------------------- principal
def main():
    ap = argparse.ArgumentParser(description="Teste de ponta a ponta do pipeline (sem tocar em produção).")
    ap.add_argument("entrada", choices=["formulario", "issue"], help="qual caminho testar")
    ap.add_argument("--banco", default="formigas")
    ap.add_argument("--fwd", default=FWD_PADRAO)
    ap.add_argument("--rev", default=REV_PADRAO)
    ap.add_argument("--email", default="")
    ap.add_argument("--manter", action="store_true")
    ap.add_argument("--so-parser", action="store_true")
    args = ap.parse_args()

    # importa o módulo certo sem conectar na planilha / sem iniciar o monitor das Issues
    os.environ["TERRASEQ_SEM_PLANILHA"] = "1"
    os.environ["TERRASEQ_SEM_ISSUES"] = "1"
    sys.path.insert(0, os.path.join(RAIZ, "src"))
    os.chdir(RAIZ)
    if args.entrada == "formulario":
        import main as m
        nome = "main.py (formulário/planilha)"
    else:
        import main_issues as m
        nome = "main_issues.py (GitHub Issues)"
    print(f"\n{'=' * 70}\nTESTE: {nome} | banco: {args.banco}\n{'=' * 70}")

    if args.entrada == "issue":
        req, erros = conferir_parser(m, args)
        erros += conferir_opcoes_do_formulario(m)
        if erros:
            print(f"\n❌ O parser da Issue perdeu {erros} campo(s). Corrija antes de testar com uma Issue real.")
            sys.exit(1)
    else:
        req = pedido_formulario(args)
    if args.so_parser:
        print("\n✅ Parser OK (modo --so-parser: BLAST não foi rodado).")
        return

    req_id = f"TESTE-{'FORM' if args.entrada == 'formulario' else 'ISSUE'}-{time.strftime('%Y%m%d-%H%M%S')}"
    pasta = os.path.join(RAIZ, "docs", "reports", req_id)
    print(f"\n🚀 Rodando o pipeline ({req_id}) -- BLAST em '{args.banco}', pode levar vários minutos ...")
    inicio = time.time()
    erros = 0
    try:
        m.run_pipeline(req, req_id)
        print(f"⏱️ pipeline terminou em {(time.time() - inicio) / 60:.1f} min")
        erros += conferir_resultado(req_id, req, pasta)
        if args.email:
            print(f"\n📧 Testando envio de e-mail para {args.email} ...")
            m.enviar_email_notificacao(args.email, req_id)
    except Exception:
        traceback.print_exc()
        erros += 1
    finally:
        if args.manter:
            print(f"\n📁 Relatório de teste mantido em docs/reports/{req_id}")
            print("   Para ver: python3 -m http.server -d docs 8000  ->  http://localhost:8000/reports/" + req_id + "/")
            print("   ⚠️ Apague antes do próximo relatório real: rm -rf docs/reports/TESTE-*")
        else:
            shutil.rmtree(pasta, ignore_errors=True)
            print(f"\n🧹 docs/reports/{req_id} apagado.")

    print("\n" + ("✅ TUDO CERTO" if not erros else f"❌ {erros} problema(s) -- veja as linhas com ❌ acima"))
    sys.exit(1 if erros else 0)


if __name__ == "__main__":
    main()
