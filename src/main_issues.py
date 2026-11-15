import time
import re
import json
import os
import shutil
import subprocess
from datetime import datetime
import csv
import sys
import requests
from Bio import Entrez
import taxonomia_local
import notificacoes
import bloqueios
import vitrine
from ecologia import REGRAS_CLASSIFICACAO_ECOLOGICA, FUNCOES_ECOLOGICAS, classificar_ecologia  # noqa: F401
from arvore_taxonomica import construir_arvore_aninhada, descobrir_rank  # noqa: F401
import pipeline
from pipeline import validate_primer, extrair_campo_flexivel, calcular_organismos_nao_capturados  # noqa: F401
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import traceback
import resource
from dotenv import load_dotenv

# Eleva o limite de arquivos abertos do processo (ulimit -n). O banco
# "eucariotos" combina dezenas de bancos BLAST numa busca só, e os maiores
# (bacteria, ascomycota, sar...) são divididos em vários volumes -- a soma
# de arquivos que o blastn precisa abrir ao mesmo tempo passa do padrão do
# Linux (1024) e causa "BLAST Database error: Cannot memory map ... Number
# of files opened: 1020". Mesmo ajuste do main.py.
try:
    limite_atual, limite_maximo = resource.getrlimit(resource.RLIMIT_NOFILE)
    novo_limite = 65536 if limite_maximo == resource.RLIM_INFINITY else min(65536, limite_maximo)
    if limite_atual < novo_limite:
        resource.setrlimit(resource.RLIMIT_NOFILE, (novo_limite, limite_maximo))
        print(f"🔧 Limite de arquivos abertos elevado de {limite_atual} para {novo_limite}.")
except (ValueError, OSError) as e:
    print(f"⚠️ Não foi possível elevar o limite de arquivos abertos automaticamente ({e}).")
    print("   Se o erro 'Cannot memory map ... .nhr' persistir, rode antes: ulimit -n 65536")

# ==========================================
# CONFIGURAÇÕES INICIAIS E API
# ==========================================
# Carrega variáveis do arquivo .env (que NÃO é versionado no Git).
# Veja .env.example para o modelo com as chaves esperadas.
load_dotenv()

def _obter_env_obrigatoria(nome):
    valor = os.environ.get(nome)
    if not valor:
        print(f"❌ Erro fatal: variável de ambiente '{nome}' não encontrada.")
        print("   Verifique se o arquivo .env existe na raiz do projeto e está preenchido.")
        print("   Use .env.example como modelo.")
        sys.exit(1)
    return valor

Entrez.email = _obter_env_obrigatoria("ENTREZ_EMAIL")

SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
EMAIL_REMETENTE = _obter_env_obrigatoria("EMAIL_REMETENTE")
EMAIL_SENHA = _obter_env_obrigatoria("EMAIL_SENHA")

# --- CONFIGURAÇÕES DA API DO GITHUB ---
GITHUB_TOKEN = _obter_env_obrigatoria("GITHUB_TOKEN")
REPO_OWNER = os.environ.get("GITHUB_REPO_OWNER", "TerraSeq")
REPO_NAME = os.environ.get("GITHUB_REPO_NAME", "TerraSeq")

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

# ==========================================
# FUNÇÕES DE APOIO E E-MAIL
# ==========================================
def enviar_email_notificacao(email_destino, req_id):
    link_pages = f"https://{REPO_OWNER}.github.io/{REPO_NAME}/reports/{req_id}/"
    notificacoes.enviar_email_sucesso(email_destino, req_id, link_pages)

# ==========================================
# FUNÇÕES DE TAXONOMIA E GITHUB PAGES
# ==========================================
def publicar_no_github(req_id):
    print("🚀 Iniciando publicação no GitHub Pages...")
    raiz_projeto = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    try:
        # Só a lista da vitrine e a pasta DESTE relatório (ver main.py).
        subprocess.run(["git", "add", vitrine.CAMINHO_VITRINE_GIT, f"docs/reports/{req_id}"], cwd=raiz_projeto, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "commit", "-m", f"Report {req_id}"], cwd=raiz_projeto, check=True, stdout=subprocess.DEVNULL)
    except subprocess.CalledProcessError as e:
        print(f"   ⚠️ Erro ao commitar as mudanças: {e}")
        return

    try:
        subprocess.run(["git", "push"], cwd=raiz_projeto, check=True, capture_output=True, text=True)
        print("   🌐 Relatório pushado com sucesso!")
        return
    except subprocess.CalledProcessError:
        # Push rejeitado (branch remota avançou, ex: outra pessoa ou o
        # próprio Claude publicando algo direto no main). Tenta sincronizar
        # sozinho em vez de deixar o relatório preso localmente.
        print("   ⚠️ Push rejeitado (remoto avançou). Tentando sincronizar automaticamente...")

    try:
        subprocess.run(["git", "pull", "--no-edit"], cwd=raiz_projeto, check=True, capture_output=True, text=True)
        subprocess.run(["git", "push"], cwd=raiz_projeto, check=True, capture_output=True, text=True)
        print("   🌐 Sincronizado com o GitHub e relatório pushado com sucesso!")
    except subprocess.CalledProcessError as e:
        print(f"   🔥 Falha ao sincronizar automaticamente com o GitHub (exit code {e.returncode}):")
        print(e.stdout or "")
        print(e.stderr or "")
        print("   ⚠️ O relatório está salvo localmente (commitado), mas precisa de um 'git pull'/merge manual para ir ao ar.")
        

def atualizar_vitrine_html(req, req_id, resultado_json=None):
    """Põe a análise na vitrine do site (docs/dados/vitrine.json).

    O nome ficou da época em que a vitrine era escrita direto no HTML; hoje só
    repassa para vitrine.adicionar_analise (scripts_auxiliares/rodar_pedidos.py
    também chama esta função).
    """
    try:
        vitrine.adicionar_analise(req, req_id, resultado_json)
    except Exception as e:
        print(f"   ⚠️ Erro ao atualizar vitrine: {e}")


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
    link_pages = f"https://{REPO_OWNER}.github.io/{REPO_NAME}/reports/{req_id}/"

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
