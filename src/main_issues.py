"""
Monitor das Issues: vigia as Issues do GitHub com o rótulo "analise-pendente"
(formulário .github/ISSUE_TEMPLATE/solicitacao_analise.yml) e, para cada uma,
roda a análise, publica o relatório, comenta o link na Issue e a fecha.

    python3 src/main_issues.py

A análise em si está em pipeline.py (a mesma do main.py); a publicação
(vitrine, git, e-mail), em publicacao.py.
"""
import os
import re
import shutil
import time
import traceback
from datetime import datetime

import requests

import bloqueios
import configuracao
import notificacoes
import pipeline
from publicacao import atualizar_vitrine_html, enviar_email_notificacao, publicar_no_github  # noqa: F401

configuracao.iniciar()

# --- API do GitHub (ler, comentar, rotular e fechar as Issues) ---
GITHUB_TOKEN = configuracao.obter_env_obrigatoria("GITHUB_TOKEN")
REPO_OWNER, REPO_NAME = configuracao.repositorio()

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}


def run_pipeline(req, req_id):
    """Roda a análise de um pedido vindo de uma Issue do GitHub. O processo todo está em
    pipeline.py (o mesmo para o formulário e para as Issues)."""
    return pipeline.run_pipeline(req, req_id, origem="ISSUE")


# ==========================================
# GITHUB API CONTROLLERS
# ==========================================
def buscar_requisicoes_github():
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues?state=open&labels=analise-pendente"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"⚠️ O GitHub recusou a conexão. Código: {response.status_code} | Motivo: {response.text}")
    except Exception as e:
        print(f"⚠️ Erro de conexão com GitHub: {e}")
    return []

def atualizar_status_issue(numero_issue, req_id, numero_analise=None):
    url_comments = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues/{numero_issue}/comments"
    link_pages = configuracao.link_relatorio(req_id)

    corpo_comentario = {"body": notificacoes.comentario_sucesso(numero_analise or numero_issue, link_pages)}
    ok = True
    r = requests.post(url_comments, headers=HEADERS, json=corpo_comentario, timeout=30)
    if r.status_code != 201:
        ok = False
        print(f"⚠️ Não consegui comentar na Issue #{numero_issue} ({r.status_code}): {r.text[:150]}")

    url_issue = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues/{numero_issue}"
    modificacoes = {
        "state": "closed",
        "labels": ["analise-concluida"]
    }
    r = requests.patch(url_issue, headers=HEADERS, json=modificacoes, timeout=30)
    if r.status_code != 200:
        ok = False
        print(f"⚠️ Não consegui fechar a Issue #{numero_issue} ({r.status_code}): {r.text[:150]}")
    if not ok:
        print("   O token do GITHUB_TOKEN precisa de permissão de ESCRITA em Issues (Issues: Read and write / escopo 'repo').")
    return ok

# Rótulos que o fluxo usa: o formulário da Issue aplica "analise-pendente" (só se
# o rótulo já existir no repositório!), o monitor troca por "running" durante a
# análise e por "analise-concluida" no fim.
ROTULOS_DO_FLUXO = {
    "analise-pendente": ("fbca04", "Aguardando processamento pelo pipeline"),
    "running": ("0e8a16", "Em processamento pelo pipeline"),
    "analise-concluida": ("1d76db", "Análise concluída"),
    "analise-com-erro": ("d73a4a", "Pedido não processado (erro ou dado inválido)"),
}

def verificar_repositorio_e_rotulos():
    """Mostra qual repositório está sendo vigiado, confere o token e cria os
    rótulos do fluxo que ainda não existirem. Nunca derruba o monitor."""
    base = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"
    print(f"\n🔎 Repositório vigiado: {REPO_OWNER}/{REPO_NAME}")
    try:
        resp = requests.get(base, headers=HEADERS, timeout=30)
    except Exception as e:
        print(f"⚠️ Não consegui falar com o GitHub: {e}")
        return
    if resp.status_code != 200:
        print(f"⚠️ O GitHub respondeu {resp.status_code} ao acessar {REPO_OWNER}/{REPO_NAME}: {resp.text[:200]}")
        print("   Confira GITHUB_TOKEN (permissão de Issues), GITHUB_REPO_OWNER e GITHUB_REPO_NAME no .env.")
        return
    dados = resp.json()
    nome_real = dados.get("full_name", "")
    if nome_real.lower() != f"{REPO_OWNER}/{REPO_NAME}".lower():
        print(f"⚠️ O repositório foi renomeado/transferido: o GitHub redirecionou para '{nome_real}'.")
        print(f"   Ajuste GITHUB_REPO_OWNER/GITHUB_REPO_NAME no .env para '{nome_real}' (senão comentar e fechar a Issue falha).")
    if not dados.get("has_issues", True):
        print("⚠️ As Issues estão DESABILITADAS neste repositório (Settings → Features → Issues).")
    print(f"   ✅ Acesso ao repositório OK ({nome_real or REPO_NAME}).")

    for nome, (cor, descricao) in ROTULOS_DO_FLUXO.items():
        try:
            r = requests.post(f"{base}/labels", headers=HEADERS, timeout=30,
                              json={"name": nome, "color": cor, "description": descricao})
        except Exception as e:
            print(f"   ⚠️ Rótulo '{nome}': erro de conexão ({e})")
            continue
        if r.status_code == 201:
            print(f"   ➕ Rótulo '{nome}' criado.")
        elif r.status_code == 422:
            print(f"   ✔️ Rótulo '{nome}' já existe.")
        else:
            print(f"   ⚠️ Rótulo '{nome}': não consegui criar ({r.status_code}) -- crie à mão em Issues → Labels.")

def parse_issue_body(body):
    sections = re.split(r'###\s+', body)
    data = {}
    for sec in sections:
        if not sec.strip(): continue
        lines = sec.strip().split('\n')
        # O formulário da Issue (solicitacao_analise.yml) usa "→" nos rótulos dos
        # primers ("Primer Forward (5' → 3')"); o parser procura "->". Sem essa
        # normalização os primers chegavam vazios em toda Issue.
        key = lines[0].strip().replace('\u2192', '->')
        value = '\n'.join(lines[1:]).strip()
        if value == "_No response_": value = ""
        data[key] = value
    
    def campo(rotulo_en, rotulo_pt, padrao):
        """Valor do campo pelo rotulo em ingles (formulario atual) ou em portugues
        (Issues abertas antes da traducao)."""
        return data.get(rotulo_en) or data.get(rotulo_pt) or padrao

    req = {
        'Nome completo': campo('Researcher Name', 'Nome do Pesquisador', 'Pesquisador'),
        'Email': campo('Notification E-mail', 'E-mail para Notificação', ''),
        'Nome do Par de Primers': campo('Primer Pair Name', 'Nome do Par de Primers', ''),
        'Primer forward': campo("Forward Primer (5' -> 3')", "Primer Forward (5' -> 3')", ''),
        'Primer reverse': campo("Reverse Primer (5' -> 3')", "Primer Reverse (5' -> 3')", ''),
        'Região alvo': campo('Target Region', 'Região Alvo', '18S'),
        'Banco de Dados': campo('Database', 'Banco de Dados', 'Protozoa'),
        'Tipo de organismo': campo('Organism Type', 'Tipo de organismo', 'Eukaryota'),
        'Máximo de Mismatches na extremidade 3': campo("Maximum 3' End Mismatches", "Máximo de Mismatches (Extremidade 3')", '3'),
        'Tamanho do amplicon: MIN': campo('Minimum Amplicon Size (bp)', 'Tamanho Mínimo do Amplicon (bp)', '3000'),
        'Tamanho do amplicon: MAX': campo('Maximum Amplicon Size (bp)', 'Tamanho Máximo do Amplicon (bp)', '8000'),
        'Temperatura de Melting mínima (Tm)': campo('Minimum Melting Temperature (Tm)', 'Temperatura de Melting mínima (Tm)', '0'),
        'E-value máximo': campo('Maximum E-value', 'E-value Máximo', '10'),
        'Cobertura mínima': campo('Minimum Coverage (%)', 'Cobertura mínima (%)', '70'),
    }
    # Os menus do formulário trazem uma descrição entre parênteses
    # ("Refseqsoil (banco completo: ...)", "Geral (todos os reinos)"); o
    # pipeline só quer o nome ("Refseqsoil", "Geral").
    for chave in ('Banco de Dados', 'Tipo de organismo'):
        req[chave] = re.sub(r'\s*\(.*\)\s*$', '', req[chave]).strip()
    req['Banco de Dados'] = notificacoes.banco_em_portugues(req['Banco de Dados'])
    return req

# ==========================================
# LOOP PRINCIPAL DO MOTOR GITHUB ISSUES
# ==========================================
# TERRASEQ_SEM_ISSUES=1 permite importar este módulo só pra reaproveitar
# run_pipeline/parse_issue_body (ex: scripts_auxiliares/testar_pipeline.py) sem
# iniciar o monitoramento das Issues.
def numero_da_analise(numero_issue):
    """Posição desta Issue entre as Issues de análise (1, 2, 3...).

    O número da Issue no GitHub não serve pra isso: Issues e PRs dividem a mesma
    sequência (a primeira Issue do repositório pode ser a #14). Aqui contamos só
    as Issues que carregam algum rótulo do fluxo (analise-pendente / running /
    analise-concluida), abertas ou fechadas, pela ordem de criação -- sem guardar
    estado local, então sobrevive a reinício do monitor. Devolve None se o GitHub
    não responder (o chamador cai no número da própria Issue)."""
    base = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues"
    numeros = {numero_issue}
    for rotulo in ROTULOS_DO_FLUXO:
        pagina = 1
        while True:
            try:
                r = requests.get(base, headers=HEADERS, timeout=30,
                                 params={"state": "all", "labels": rotulo, "per_page": 100, "page": pagina})
            except Exception:
                return None
            if r.status_code != 200:
                return None
            itens = r.json()
            numeros.update(i["number"] for i in itens if "pull_request" not in i)
            if len(itens) < 100:
                break
            pagina += 1
    return sorted(numeros).index(numero_issue) + 1


def titulo_com_numero(titulo_atual, numero_analise, nome_par):
    """"[Analysis] - texto" -> "[Analysis #3] - texto". Se o título veio vazio
    (só o prefixo do formulário), usa o nome do par de primers."""
    resto = re.sub(r'^\s*\[[^\]]*\]\s*-?\s*', '', titulo_atual or '').strip()
    return f"[Analysis #{numero_analise}] - {resto or nome_par or 'unnamed'}"


def monitorar_issues():
    verificar_repositorio_e_rotulos()
    print("\n✅ SCRIPT HÍBRIDO ONLINE - Monitorando GitHub Issues (rótulo 'analise-pendente')...")

    # Issues já tentadas nesta execução do monitor. Cada Issue é processada no
    # máximo UMA vez: se o GitHub não deixar marcar/fechar (token sem escrita) ou
    # a análise falhar, repetir a cada 15s reprocessaria tudo sem parar (BLAST,
    # linha duplicada na vitrine, push e e-mail a cada rodada). Para tentar de
    # novo uma Issue que falhou, corrija o problema e reinicie o monitor.
    tentadas = set()

    while True:
        try:
            issues = buscar_requisicoes_github()
            for issue in issues:
                numero_issue = issue['number']
                if numero_issue in tentadas:
                    continue
                tentadas.add(numero_issue)
                corpo = issue['body']

                print(f"\n🔔 Nova requisição encontrada na Issue #{numero_issue}!")

                url_issue = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues/{numero_issue}"
                # Numera a Issue ("[Analysis #1] - ...") junto com a marcação 'running'.
                numero_analise = numero_da_analise(numero_issue) or numero_issue
                nome_par = parse_issue_body(corpo).get('Nome do Par de Primers', '')
                titulo = titulo_com_numero(issue.get('title', ''), numero_analise, nome_par)
                print(f"   🏷️ Análise #{numero_analise}: {titulo}")
                r = requests.patch(url_issue, headers=HEADERS, json={"labels": ["running"], "title": titulo}, timeout=30)
                if r.status_code != 200:
                    print(f"🛑 Não consegui marcar a Issue #{numero_issue} como 'running' ({r.status_code}): {r.text[:150]}")
                    print("   O GITHUB_TOKEN precisa de permissão de ESCRITA em Issues (fine-grained: Issues → Read and write;")
                    print("   clássico: escopo 'repo'). A Issue NÃO foi processada. Corrija o token e reinicie o monitor.")
                    continue

                req_mapeado = {}
                hoje_str = datetime.now().strftime('%Y%m%d')
                req_id = f"REQ-{hoje_str}-ISSUE{numero_issue:04d}"
                pipeline_ok = False
                try:
                    req_mapeado = parse_issue_body(corpo)

                    caminho_relatorio, resultado_json = run_pipeline(req_mapeado, req_id)
                    pipeline_ok = True
                    with bloqueios.bloqueio("publicacao", "⏳ Aguardando outra publicação terminar..."):
                        atualizar_vitrine_html(req_mapeado, req_id, resultado_json)
                        publicar_no_github(req_id)

                    email_usuario = req_mapeado.get('Email', '')
                    enviar_email_notificacao(email_usuario, req_id)

                    fechou = atualizar_status_issue(numero_issue, req_id, numero_analise)

                    if fechou:
                        print(f"✨ Issue #{numero_issue} finalizada com sucesso! Aguardando próximas...")
                    else:
                        print(f"⚠️ Issue #{numero_issue}: relatório publicado, mas não consegui comentar/fechar a Issue (veja acima). Aguardando próximas...")
                except Exception as e:
                    print(f"\n🔥 ERRO ao processar a Issue #{numero_issue}: {e}")
                    traceback.print_exc()
                    if not pipeline_ok:
                        # evita que a pasta pela metade entre no próximo "git add docs/"
                        shutil.rmtree(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'docs', 'reports', req_id), ignore_errors=True)
                    if isinstance(e, notificacoes.PedidoInvalido):
                        comentario = notificacoes.comentario_pedido_invalido(numero_analise, e.problemas)
                    else:
                        comentario = notificacoes.comentario_erro_interno(numero_analise)
                    try:
                        requests.post(f"{url_issue}/comments", headers=HEADERS, timeout=30, json={"body": comentario})
                        requests.patch(url_issue, headers=HEADERS, timeout=30,
                                       json={"state": "closed", "labels": ["analise-com-erro"]})
                    except Exception:
                        pass
                    notificacoes.notificar_falha(req_mapeado.get('Email', ''), req_id, e, req_mapeado, "issue")

            time.sleep(15)

        except Exception as e:
            print(f"\n🔥 ERRO NA VARREDURA DE ISSUES: {e}")
            time.sleep(15)


if os.environ.get("TERRASEQ_SEM_ISSUES") != "1":
    monitorar_issues()
