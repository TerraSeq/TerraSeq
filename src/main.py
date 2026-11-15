import gspread
from google.oauth2.service_account import Credentials
import time
import re
import json
import os
import shutil
import subprocess
from datetime import datetime
import csv
import sys
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

# --- CONFIGURAÇÕES INICIAIS ---

# Eleva o limite de arquivos abertos do processo (ulimit -n). O banco
# "eucariotos" combina dezenas de bancos BLAST numa busca só, e os maiores
# (bacteria, ascomycota, sar...) são divididos em vários volumes -- a soma
# de arquivos que o blastn precisa abrir ao mesmo tempo passou do padrão do
# Linux (1024) depois que os grupos novos foram indexados, causando
# "BLAST Database error: Cannot memory map ... Number of files opened: 1020".
# Isso sobe o limite do processo (não precisa de sudo nem mexer no shell),
# até o teto que o sistema permitir.
try:
    limite_atual, limite_maximo = resource.getrlimit(resource.RLIMIT_NOFILE)
    novo_limite = 65536 if limite_maximo == resource.RLIM_INFINITY else min(65536, limite_maximo)
    if limite_atual < novo_limite:
        resource.setrlimit(resource.RLIMIT_NOFILE, (novo_limite, limite_maximo))
        print(f"🔧 Limite de arquivos abertos elevado de {limite_atual} para {novo_limite}.")
except (ValueError, OSError) as e:
    print(f"⚠️ Não foi possível elevar o limite de arquivos abertos automaticamente ({e}).")
    print("   Se o erro 'Cannot memory map ... .nhr' persistir, rode antes: ulimit -n 65536")
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

GITHUB_REPO_OWNER = os.environ.get("GITHUB_REPO_OWNER", "TerraSeq")
GITHUB_REPO_NAME = os.environ.get("GITHUB_REPO_NAME", "pipeline_genoma")

# TERRASEQ_SEM_PLANILHA=1 permite importar este módulo só pra reaproveitar
# run_pipeline (ex: scripts_auxiliares/reprocessar_relatorios.py) sem conectar
# na planilha do Google nem iniciar o monitoramento das submissões.
SEM_PLANILHA = os.environ.get("TERRASEQ_SEM_PLANILHA") == "1"

if not SEM_PLANILHA:
    caminho_credenciais = os.path.join(
        os.path.dirname(__file__),
        os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json")
    )
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_file(caminho_credenciais, scopes=scopes)
    client = gspread.authorize(credentials)

    NOME_DA_PLANILHA = os.environ.get("NOME_DA_PLANILHA", "Submissoes_Primers_Pipeline")
    planilha = client.open(NOME_DA_PLANILHA).sheet1


def enviar_email_notificacao(email_destino, req_id):
    link_pages = f"https://{GITHUB_REPO_OWNER}.github.io/{GITHUB_REPO_NAME}/reports/{req_id}/"
    notificacoes.enviar_email_sucesso(email_destino, req_id, link_pages)

def publicar_no_github(req_id):
    print("🚀 Iniciando publicação no GitHub Pages...")
    raiz_projeto = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    try:
        # Só a lista da vitrine e a pasta DESTE relatório: um "git add docs/" levaria
        # junto a pasta pela metade de outra análise que está rodando ao mesmo tempo.
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
    """Roda a análise de um pedido vindo da planilha (Google Forms). O processo todo está em
    pipeline.py (o mesmo para o formulário e para as Issues)."""
    return pipeline.run_pipeline(req, req_id, origem="PLANILHA")


def _erro_de_rede(e):
    """Falha transitória de conexão/servidor (vale tentar de novo), não um bug."""
    if isinstance(e, (ConnectionError, TimeoutError)):  # inclui ConnectionResetError, BrokenPipeError
        return True
    modulo = type(e).__module__ or ""
    if modulo.startswith(("requests.", "urllib3.", "google.auth.exceptions", "http.client", "ssl", "socket")):
        return True
    codigo = getattr(getattr(e, "response", None), "status_code", None)  # gspread.APIError
    return codigo in (429, 500, 502, 503, 504)


def reconectar_planilha():
    """Abre uma conexão nova com o Google Sheets. Terminal parado a noite toda
    deixa a conexão antiga morrer ("Connection reset by peer"); repetir com ela
    não adianta."""
    global credentials, client, planilha
    credentials = Credentials.from_service_account_file(caminho_credenciais, scopes=scopes)
    client = gspread.authorize(credentials)
    planilha = client.open(NOME_DA_PLANILHA).sheet1


# Formulario em ingles: titulos das perguntas (cabecalhos da planilha) e opcoes de
# banco em ingles viram as chaves em portugues que o resto do pipeline usa. Os
# titulos/opcoes em portugues continuam funcionando (linhas antigas da planilha).
CABECALHOS_EN_PT = {
    "full name": "Nome completo",
    "institution": "Instituição",
    "forward primer": "Primer forward",
    "reverse primer": "Primer reverse",
    "primer pair name": "Nome do Par de Primers",
    "target region": "Região alvo",
    "database": "Banco de Dados",
    "organism type": "Tipo de organismo",
    "maximum 3' end mismatches": "Máximo de Mismatches na extremidade 3",
    "amplicon size: min": "Tamanho do amplicon: MIN",
    "amplicon size: max": "Tamanho do amplicon: MAX",
    "minimum melting temperature (tm)": "Temperatura de Melting mínima (Tm)",
    "maximum e-value": "E-value máximo",
    "minimum coverage": "Cobertura mínima",
    "hit limit": "Limite de hits",
}


def traduzir_registro(registro):
    """Troca cabecalhos e opcao de banco em ingles pelos equivalentes em portugues."""
    traduzido = {}
    for nome, valor in registro.items():
        chave = CABECALHOS_EN_PT.get(" ".join(nome.split()).lower(), nome)
        # Se a planilha tiver as duas colunas (antiga em PT e nova em EN), vale a preenchida.
        if chave in traduzido and not str(valor).strip():
            continue
        traduzido[chave] = valor
    if "Banco de Dados" in traduzido:
        traduzido["Banco de Dados"] = notificacoes.banco_em_portugues(traduzido["Banco de Dados"])
    return traduzido


def ler_registros(planilha):
    """Lê as linhas da planilha como dicionários {cabeçalho: valor}.

    Substitui planilha.get_all_records(), que levanta GSpreadException e derruba
    o monitor inteiro quando a linha de cabeçalho tem colunas repetidas -- o
    que acontece sozinho na planilha ligada ao Google Forms (ex: duas colunas
    "Column 17" quando alguém edita o formulário). Aqui colunas sem cabeçalho
    são ignoradas e, se um cabeçalho se repete, vale a primeira coluna.
    Mantém uma entrada por linha da planilha (inclusive vazias), então
    "linha_planilha = índice + 2" continua certo."""
    valores = planilha.get_all_values()
    if not valores:
        return []
    colunas = []
    vistos = set()
    for i, cabecalho in enumerate(valores[0]):
        nome = str(cabecalho).strip()
        if nome and nome not in vistos:
            vistos.add(nome)
            colunas.append((i, nome))
    repetidos = [str(c).strip() for c in valores[0] if str(c).strip() and valores[0].count(c) > 1]
    if repetidos and not getattr(ler_registros, "_avisou", False):
        ler_registros._avisou = True
        print(f"⚠️ A planilha tem cabeçalhos repetidos {sorted(set(repetidos))}: uso só a primeira coluna de cada. "
              "Vale apagar/renomear as colunas repetidas na planilha.")
    return [
        traduzir_registro({nome: (linha[i] if i < len(linha) else "") for i, nome in colunas})
        for linha in valores[1:]
    ]


def monitorar_planilha():
    print("\n✅ SCRIPT ONLINE - Monitorando Planilha...")
    try:
        cabecalhos = planilha.row_values(1)
        COL_STATUS = cabecalhos.index('Status') + 1
        COL_LINK = cabecalhos.index('Result_path') + 1
    except ValueError:
        print("❌ Erro fatal: Colunas Status ou Result_path não encontradas.")
        sys.exit()

    def celula(linha, coluna, valor):
        """update_cell com 4 tentativas (reconectando) se a rede cair na hora."""
        ultima = None
        for tentativa, espera in enumerate((0, 3, 10, 30), 1):
            if espera:
                time.sleep(espera)
            try:
                planilha.update_cell(linha, coluna, valor)
                return
            except Exception as e:
                if not _erro_de_rede(e):
                    raise
                ultima = e
                print(f"   ⚠️ Falha de rede ao atualizar a planilha ({type(e).__name__}); tentativa {tentativa}/4")
                try:
                    reconectar_planilha()
                except Exception:
                    pass
        raise ultima

    falhas_rede = 0
    while True:
        try:
            registros = ler_registros(planilha)
            for index, req in enumerate(registros):
                linha_planilha = index + 2 
            
                # Se não tiver nenhum primer preenchido, é uma linha fantasma. Pule para a próxima!
                if str(req.get('Primer forward', '')).strip() == '':
                    continue
                # --------------------------------------
            
                status_atual = str(req.get('Status', '')).strip().lower()
            
                if status_atual == '' or status_atual == 'pending':
                    print(f"\n🔔 Nova requisição encontrada na linha {linha_planilha}!")
                    # ... resto do código continua igualzinho
                    celula(linha_planilha, COL_STATUS, 'running') 
                
                    # O ID do relatório precisa ser único por SUBMISSÃO, não por
                    # linha da planilha -- número de linha do Google Sheets NÃO É
                    # estável: se uma linha acima for removida (ex: ao limpar
                    # 'Status' manualmente pra reprocessar), todas as linhas
                    # abaixo sobem uma posição. Duas submissões diferentes no
                    # mesmo dia podem cair na mesma linha e gerar o MESMO
                    # REQ-ID, e a segunda sobrescreve os arquivos da primeira
                    # silenciosamente (aconteceu de verdade: duas submissões
                    # distintas com REQ-20260921-0073, uma delas perdida).
                    # Fix: usa o Timestamp que o próprio Google Forms grava na
                    # linha (é único por submissão, não muda se a linha se
                    # mover) em vez do número da linha. Cai pro esquema antigo
                    # (data + linha) só se o Timestamp estiver ausente/em
                    # formato inesperado.
                    hoje_str = datetime.now().strftime('%Y%m%d')
                    timestamp_str = str(req.get('Timestamp', '')).strip()
                    try:
                        timestamp_dt = datetime.strptime(timestamp_str, '%m/%d/%Y %H:%M:%S')
                        req_id = f"REQ-{timestamp_dt.strftime('%Y%m%d-%H%M%S')}"
                    except ValueError:
                        req_id = f"REQ-{hoje_str}-{linha_planilha:04d}"

                    # Salvaguarda final: nunca sobrescreve um relatório já
                    # existente, mesmo que o req_id acima colida por algum
                    # motivo imprevisto (ex: Timestamp ausente caindo no
                    # fallback por linha, que ainda pode colidir).
                    raiz_projeto_loop = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
                    req_id_base = req_id
                    sufixo = 2
                    while os.path.exists(os.path.join(raiz_projeto_loop, "docs", "reports", req_id)):
                        req_id = f"{req_id_base}-{sufixo}"
                        sufixo += 1

                    try:
                        caminho_relatorio, resultado_json = run_pipeline(req, req_id)
                    except Exception as e:
                        # Antes o erro só aparecia no terminal e a linha ficava "running"
                        # pra sempre, sem o usuário saber. Agora: planilha, e-mail ao
                        # usuário (o que corrigir) e, em erro interno, e-mail à equipe.
                        print(f"\n🔥 ERRO ao processar a linha {linha_planilha} ({req_id}): {e}")
                        traceback.print_exc()
                        shutil.rmtree(os.path.join(raiz_projeto_loop, "docs", "reports", req_id), ignore_errors=True)
                        celula(linha_planilha, COL_STATUS, 'error')
                        celula(linha_planilha, COL_LINK, "ERRO: " + notificacoes.resumo_do_erro(e))
                        notificacoes.notificar_falha(str(req.get('Email', '')).strip(), req_id, e, req, "planilha")
                        continue

                    # Vitrine + git: um processo por vez (formulário e Issues podem
                    # terminar juntos).
                    with bloqueios.bloqueio("publicacao", "⏳ Aguardando outra publicação terminar..."):
                        atualizar_vitrine_html(req, req_id, resultado_json)
                        publicar_no_github(req_id)

                    email_usuario = str(req.get('Email', '')).strip()
                    enviar_email_notificacao(email_usuario, req_id)

                    # A planilha (só contabilidade) por último: se a rede cair aqui, o
                    # relatório já foi publicado e o usuário já foi avisado.
                    celula(linha_planilha, COL_LINK, caminho_relatorio)
                    celula(linha_planilha, COL_STATUS, 'completed')

                    print("✨ Processamento da linha concluído com sucesso. Aguardando próximas...")
                    
            falhas_rede = 0
            time.sleep(10)
        except Exception as e:
            if _erro_de_rede(e):
                falhas_rede += 1
                espera = min(10 * 2 ** (falhas_rede - 1), 120)
                print(f"\n⚠️ Falha de rede com o Google Sheets ({type(e).__name__}); nova tentativa em {espera}s (falha nº {falhas_rede}).")
                time.sleep(espera)
                try:
                    reconectar_planilha()
                    print("   🔌 Reconectado ao Google Sheets.")
                except Exception as e2:
                    print(f"   ⚠️ Ainda sem conexão ({type(e2).__name__}).")
                continue
            print(f"\n🔥 ERRO FATAL DETECTADO NA EXECUÇÃO PRINCIPAL:")
            traceback.print_exc()
            if isinstance(e, subprocess.CalledProcessError):
                print("\n📋 SAÍDA DO COMANDO QUE FALHOU (stderr):")
                print(e.stderr or "(vazio)")
                print("\n📋 SAÍDA DO COMANDO QUE FALHOU (stdout):")
                print(e.stdout or "(vazio)")
            print("Reiniciando a varredura em 10 segundos...")
            time.sleep(10)


if not SEM_PLANILHA:
    monitorar_planilha()
