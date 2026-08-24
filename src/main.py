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
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import traceback
from dotenv import load_dotenv

# --- CONFIGURAÇÕES INICIAIS ---
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

caminho_credenciais = os.path.join(
    os.path.dirname(__file__),
    os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json")
)
scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_file(caminho_credenciais, scopes=scopes)
client = gspread.authorize(credentials)

NOME_DA_PLANILHA = os.environ.get("NOME_DA_PLANILHA", "Submissoes_Primers_Pipeline")
planilha = client.open(NOME_DA_PLANILHA).sheet1

# ==========================================
# MOTOR DE CLASSIFICAÇÃO ECOLÓGICA (Global Soil Biodiversity Atlas)
#
# "Grande Grupo"     -> Capítulo II (Diversidade dos Organismos do Solo)
# "Função Ecológica" -> Capítulo IV, p.112 (Ecosystem Functions and Services)
#
# O Cap. IV (p.112) define 4 grupos funcionais para a biota do solo:
#   1) Microrganismos                  -> Bactérias, Archaea, Fungos
#   2) Micropredadores                 -> Protistas, Nematoides, Tardígrados, Rotíferos
#   3) Decompositores da Serrapilheira -> meso/macrofauna que fragmenta a
#      serrapilheira: Ácaros, Colêmbolos, Isópodes, Miriápodes, larvas de insetos
#   4) Engenheiros do Ecossistema       -> Minhocas, Enquitreídeos, Formigas, Cupins
#
# Grupos que existem no Cap. II mas NÃO se encaixam nos 4 grupos funcionais do
# Cap. IV (Moluscos, Plantas/raízes, Vírus, Megafauna/Vertebrados) recebem a
# função "Fora do Escopo do Atlas (Cap.4)". Eles continuam aparecendo
# normalmente na árvore taxonômica, mas ficam isolados na árvore funcional.
# ==========================================

# Cada item: (Grande Grupo, Função Ecológica, [termos de busca na linhagem do NCBI])
# A lista é avaliada NA ORDEM: o primeiro grupo cujo termo aparecer na linhagem
# "vence". Por isso grupos mais ESPECÍFICOS (ex: Enchytraeidae) vêm ANTES de
# grupos mais GENÉRICOS que os englobam (ex: Oligochaeta -> Minhocas).
# ==========================================
# MOTOR DE CLASSIFICAÇÃO ECOLÓGICA (Atlas)
# Formato: (Grupo, Tamanho Biológico, Função Ecológica, [termos])
# ==========================================

REGRAS_CLASSIFICACAO_ECOLOGICA = [
    # --- Engenheiros do Ecossistema ---
    ("Enquitreídeos", "Mesofauna / Macrofauna", "Engenheiros do Ecossistema", ["enchytraeidae"]),
    ("Formigas", "Macrofauna", "Engenheiros do Ecossistema", ["formicidae"]),
    ("Cupins", "Macrofauna", "Engenheiros do Ecossistema", ["isoptera", "termitoidae", "termitidae", "rhinotermitidae", "termopsidae", "kalotermitidae"]),
    ("Minhocas", "Macrofauna", "Engenheiros do Ecossistema", ["lumbricina", "lumbricidae", "megascolecidae", "glossoscolecidae", "moniligastridae", "ocnerodrilidae", "acanthodrilidae", "criodrilidae", "oligochaeta"]),

    # --- Decompositores da Serrapilheira ---
    ("Ácaros", "Mesofauna", "Decompositores da Serrapilheira", ["acari", "acariformes", "parasitiformes", "oribatida", "mesostigmata", "trombidiformes", "sarcoptiformes", "ixodida"]),
    ("Colêmbolos, Proturos e Dipluros", "Mesofauna", "Decompositores da Serrapilheira", ["collembola", "protura", "diplura"]),
    ("Isópodes", "Macrofauna", "Decompositores da Serrapilheira", ["isopoda", "oniscidea"]),
    ("Miriápodes", "Macrofauna", "Decompositores da Serrapilheira", ["myriapoda", "diplopoda", "chilopoda", "symphyla", "pauropoda"]),
    ("Insetos (Adultos e Larvas)", "Macrofauna", "Decompositores da Serrapilheira", ["coleoptera", "diptera", "lepidoptera", "hexapoda", "insecta"]),

    # --- Micropredadores ---
    ("Aracnídeos (Aranhas e Escorpiões)", "Macrofauna", "Micropredadores", ["arachnida", "araneae", "pseudoscorpiones", "scorpiones", "opiliones"]),
    ("Platelmintos", "Macrofauna", "Micropredadores", ["platyhelminthes", "turbellaria", "geoplanidae"]),
    ("Protistas", "Microfauna", "Micropredadores", ["excavata", "nuclearia", "ancyromonas", "fonticula", "rozella", "breviata", "apusomonadida", "amoebozoa", "alveolata", "ciliophora", "euglenozoa", "cercozoa", "apicomplexa", "heterolobosea", "foraminifera", "rhizaria", "stramenopiles", "protista"]),
    ("Nematoides", "Microfauna", "Micropredadores", ["nematoda"]),
    ("Tardígrados", "Microfauna", "Micropredadores", ["tardigrada"]),
    ("Rotíferos", "Microfauna", "Micropredadores", ["rotifera"]),

    # --- Microrganismos ---
    ("Fungos", "Microrganismos", "Microrganismos", ["fungi", "ascomycota", "basidiomycota", "mucoromycota", "chytridiomycota", "zoopagomycota", "glomeromycota"]),
    ("Archaea", "Microrganismos", "Microrganismos", ["archaea"]),
    ("Bactérias", "Microrganismos", "Microrganismos", ["bacteria", "cyanobacteria", "proteobacteria", "firmicutes", "actinobacteria"]),

    # --- Fora do Escopo Principal ---
    ("Moluscos", "Macrofauna / Megafauna", "Fora do Escopo Principal", ["mollusca", "gastropoda"]),
    ("Plantas (Raízes)", "Flora", "Fora do Escopo Principal", ["viridiplantae", "embryophyta"]),
    ("Vírus", "Vírus", "Fora do Escopo Principal", ["viruses", "viricota", "riboviria"]),
    ("Megafauna (Vertebrados)", "Megafauna", "Fora do Escopo Principal", ["mammalia", "reptilia", "amphibia", "vertebrata"]),
]

FUNCOES_ECOLOGICAS = sorted({f for _, _, f, _ in REGRAS_CLASSIFICACAO_ECOLOGICA} | {"Função Indefinida"})

def classificar_ecologia(linhagem):
    tax_str = " ".join(linhagem).lower()
    for grande_grupo, tamanho, funcao_ecologica, termos in REGRAS_CLASSIFICACAO_ECOLOGICA:
        if any(termo in tax_str for termo in termos):
            return grande_grupo, tamanho, funcao_ecologica
    return "Não Classificado", "Indefinido", "Função Indefinida"


def validate_primer(seq):
    seq = str(seq).strip()
    if not (10 <= len(seq) <= 40): return False
    if not re.match(r"^[ACGTRYSWKMBDHVNacgtryswkmbdhvn]+$", seq): return False
    return True

def enviar_email_notificacao(email_destino, req_id):
    print("📧 Preparando disparo de e-mail...")
    if not email_destino or "@" not in email_destino: 
        print(f"   ⏩ E-mail ignorado: Destinatário ausente ou inválido ({email_destino}).")
        return
    link_pages = f"https://{GITHUB_REPO_OWNER}.github.io/{GITHUB_REPO_NAME}/reports/{req_id}/"
    msg = MIMEMultipart()
    msg['From'] = EMAIL_REMETENTE
    msg['To'] = email_destino
    msg['Subject'] = f"🧬 Análise in silico Concluída ({req_id})"
    corpo = f"Olá,\n\nSua simulação de PCR foi concluída com sucesso!\nID: {req_id}\n\nAcesse o relatório: {link_pages}\n\n⚠️ Aviso Importante: O servidor web leva de 1 a 2 minutos para realizar a publicação dos arquivos. Se você acessar o link e esbarrar em um 'Erro 404' (Página não encontrada), não se preocupe! Aguarde alguns instantes e atualize a página (Ctrl + F5).\n\nAtt,\\Equipe de Bioinformática"
    msg.attach(MIMEText(corpo, 'plain', 'utf-8'))
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10)
        server.starttls()
        server.login(EMAIL_REMETENTE, EMAIL_SENHA)
        server.sendmail(EMAIL_REMETENTE, email_destino, msg.as_string())
        server.quit()
        print(f"   ✅ E-mail enviado com sucesso para: {email_destino}")
    except Exception as e:
        print(f"   ⚠️ Erro ao enviar e-mail: {e}")

def descobrir_rank(taxa, profundidade, tamanho_total):
    t = taxa.lower()
    if t in ["bacteria", "archaea", "eukaryota", "viruses"]: return "domain"
    if t in ["fungi", "metazoa", "viridiplantae"]: return "kingdom"
    if t.endswith("ota") or t.endswith("mycota") or t.endswith("phyta"): return "phylum"
    if (t.endswith("ia") and profundidade < 6) or t.endswith("mycetes") or t.endswith("opsida") or t.endswith("phyceae"): return "class"
    if t.endswith("ales"): return "order"
    if t.endswith("aceae") or t.endswith("idae"): return "family"
    if profundidade == tamanho_total - 1: return "species"
    if profundidade == tamanho_total - 2: return "genus"
    return "clade"

def extrair_campo_flexivel(dicionario_linha, palavra_chave, padrao="N/A"):
    """ Busca colunas no CSV ignorando maiúsculas/minúsculas """
    for coluna, valor in dicionario_linha.items():
        if coluna and palavra_chave.lower() in coluna.lower():
            return valor
    return padrao

def construir_arvore_aninhada(lista_ids, total_matches, hits_data_map, total_sequences_banco):
    total_organismos = len(lista_ids)
    print(f"🌳 Consultando NCBI para {total_organismos} organismos únicos...")
    paths = []
    meta_dict = {} 
    
    # DICIONÁRIO PARA A CLASSIFICAÇÃO FUNCIONAL (Cap. 4, p.112)
    # Gerado a partir de FUNCOES_ECOLOGICAS, então cobre automaticamente os
    # 4 grupos do Atlas + "Fora do Escopo do Atlas (Cap.4)" + "Função Indefinida".
    functional_roles = {funcao: {} for funcao in FUNCOES_ECOLOGICAS}
    
    for index, subject_id in enumerate(lista_ids, 1):
        print(f"   ⏳ Baixando dados [{index}/{total_organismos}]: {subject_id}...", end="\r")
        try:
            # CORREÇÃO: Pega o ID após o último | ou antes do primeiro | se não tiver prefixo.
            # Se for gb|JBAMJC...| ele pega o item do meio.
            partes = subject_id.split('|')
            acc = partes[1] if len(partes) > 1 and partes[0].lower() in ['gb', 'ref', 'emb', 'dbj', 'gi'] else partes[0]
            acc = acc.split('.')[0]  # Remove a versão do Accession (.1)
            handle = Entrez.efetch(db="nucleotide", id=acc, retmode="xml")
            records = Entrez.read(handle)
            handle.close()
            if records:
                rec = records[0]
                linhagem = rec["GBSeq_taxonomy"].split("; ")
                especie = rec["GBSeq_organism"]
                linhagem.append(especie)
                if linhagem[0].lower() == "cellular organisms":
                    linhagem.pop(0)
                paths.append(linhagem)

                if especie not in meta_dict:
                    meta_dict[especie] = {
                        "info": {
                            "acc": rec.get("GBSeq_primary-accession", acc),
                            "desc": rec.get("GBSeq_definition", "Descrição indisponível"),
                            "length": rec.get("GBSeq_length", "N/A")
                        },
                        "amplicons": []
                    }
                
                # ---> INJETAR ESTA PARTE NOVA LOGO ABAIXO DO paths.append <---
                grupo, tamanho, funcao = classificar_ecologia(linhagem)
                
                if grupo not in functional_roles[funcao]:
                    # Agora criamos um dicionário que guarda o tamanho e a lista de espécies
                    functional_roles[funcao][grupo] = {"tamanho": tamanho, "especies": []}
                    
                functional_roles[funcao][grupo]["especies"].append({
                    "especie": especie,
                    "id": acc,
                    "matches": len(hits_data_map.get(subject_id, []))
                })
                
                if subject_id in hits_data_map:
                    meta_dict[especie]["amplicons"].extend(hits_data_map[subject_id])
                    
        except Exception:
            paths.append(["Unclassified"])
        
        time.sleep(0.4) 

    print(f"\n   ✅ Árvore construída com sucesso para {total_organismos} organismos!")

    root = {"name": "Root", "rank": "root", "matches": total_matches, "coverage": 1.0, "children": []}
    for path in paths:
        current_node = root
        tamanho_path = len(path)
        for depth, taxa in enumerate(path):
            rank_correto = descobrir_rank(taxa, depth, tamanho_path)
            found_child = None
            for child in current_node["children"]:
                if child["name"] == taxa: found_child = child; break
            if found_child:
                found_child["matches"] += 1
                current_node = found_child
            else:
                new_node = {"name": taxa, "rank": rank_correto, "matches": 1, "coverage": 0.0, "children": []}
                current_node["children"].append(new_node)
                current_node = new_node

    def calc_coverage(node):
        node["coverage"] = round(node["matches"] / total_matches, 4) if total_matches > 0 else 0.0
        for child in node["children"]: calc_coverage(child)
    calc_coverage(root)

    return root, meta_dict, functional_roles

def publicar_no_github(req_id):
    print("🚀 Iniciando publicação no GitHub Pages...")
    try:
        raiz_projeto = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        subprocess.run(["git", "add", "docs/"], cwd=raiz_projeto, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "commit", "-m", f"Report {req_id}"], cwd=raiz_projeto, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "push"], cwd=raiz_projeto, check=True, stdout=subprocess.DEVNULL)
        print("   🌐 Relatório pushado com sucesso!")
    except Exception as e:
        print(f"   ⚠️ Erro ao empurrar pro Git: {e}")
        
        
def atualizar_vitrine_html(req, req_id, resultado_json=None):
    print("🖥️ Atualizando painel de resultados na página inicial...")

    raiz_projeto = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..')
    )

    caminho_index = os.path.join(
        raiz_projeto,
        "docs/index.html"
    )

    # Dados
    fwd = str(req.get('Primer forward', '')).strip().upper()
    rev = str(req.get('Primer reverse', '')).strip().upper()
    alvo = str(req.get('Região alvo', 'Não informada')).strip()
    banco = str(req.get('Banco de Dados', 'Protozoa')).strip()
    data_hoje = datetime.now()
    data_hoje_br = data_hoje.strftime("%d/%m/%Y")
    data_hoje_iso = data_hoje.strftime("%Y-%m-%d")

    resultado_json = resultado_json or {}
    nome_par = str(resultado_json.get('primers', {}).get('pair_name', '')).strip() or f"Par {alvo}"
    mean_amp = resultado_json.get('summary', {}).get('mean_amplicon_size')
    try:
        amplicon_int = int(round(float(mean_amp)))
    except (TypeError, ValueError):
        amplicon_int = 0
    amplicon_display = f"{amplicon_int} bp" if amplicon_int > 0 else "N/D"

    marcador_alvo = "<!-- NOVAS_LINHAS -->"

    nova_linha = f"""
                    <tr data-amplicon="{amplicon_int}" data-date="{data_hoje_iso}">
                        <td><strong>{req_id}</strong></td>
                        <td>{nome_par}</td>
                        <td>{alvo}</td>
                        <td>{banco}</td>
                        <td style="font-family: monospace; color: var(--primary-color); line-height: 1.5;">
                            <span style="color: #666; font-weight: 600; font-family: 'Segoe UI', sans-serif;">F:</span> {fwd}<br>
                            <span style="color: #666; font-weight: 600; font-family: 'Segoe UI', sans-serif;">R:</span> {rev}
                        </td>
                        <td>{amplicon_display}</td>
                        <td>{data_hoje_br}</td>
                        <td>
                            <span class="status-badge">
                                Concluído
                            </span>
                        </td>
                        <td>
                            <a href="reports/{req_id}/"
                               class="btn btn-primary"
                               style="padding: 6px 12px; font-size: 0.85em;">
                               Ver Relatório
                            </a>
                        </td>
                    </tr>
                    """

    try:
        with open(caminho_index, 'r', encoding='utf-8') as f:
            conteudo = f.read()

        if marcador_alvo in conteudo:

            novo_conteudo = conteudo.replace(
                marcador_alvo,
                nova_linha + "\n" + marcador_alvo
            )

            with open(caminho_index, 'w', encoding='utf-8') as f:
                f.write(novo_conteudo)

            print("   ✅ Vitrine atualizada com sucesso!")

        else:
            print("   ⚠️ Marcador não encontrado no index.html!")

    except Exception as e:
        print(f"   ⚠️ Erro ao atualizar vitrine: {e}")


def run_pipeline(req, req_id):
    raiz_projeto = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    pasta_resultado = os.path.join(raiz_projeto, f"docs/reports/{req_id}")
    os.makedirs(pasta_resultado, exist_ok=True)
    
    fwd = str(req.get('Primer forward', '')).strip().upper()
    rev = str(req.get('Primer reverse', '')).strip().upper()
    alvo_para_nome = str(req.get('Região alvo', '')).strip()
    nome_par = str(req.get('Nome do Par de Primers', '')).strip()
    if not nome_par:
        nome_par = f"Par {alvo_para_nome}" if alvo_para_nome else f"Par {req_id}"

    caminho_primer = os.path.join(pasta_resultado, "primer.fasta")
    with open(caminho_primer, "w") as f:
        f.write(f">Ensaio_{req_id}|Target|fwd\n{fwd}\n")
        f.write(f">Ensaio_{req_id}|Target|rev\n{rev}\n")

    min_size = str(req.get('Tamanho do amplicon: MIN', 20) or 20)
    max_size = str(req.get('Tamanho do amplicon: MAX', 9999) or 9999)
    mismatches = int(req.get('Máximo de Mismatches na extremidade 3', 0) or 0)
    e_value = str(req.get('E-value máximo', 10.0) or 10.0)
    cobertura = str(req.get('Cobertura mínima', 0) or 0)
    max_hits = str(req.get('Limite de hits', 30000) or 30000)
    tm_min = str(req.get('Temperatura de Melting mínima (Tm)', 0) or 0)

    # ==========================================
    # SELEÇÃO DINÂMICA DO BANCO DE DADOS (ATLAS)
    # ==========================================
    banco_selecionado = str(req.get('Banco de Dados', 'refseqsoil')).strip().lower()
    
    # --- Mapeamento Dinâmico do Banco Completo Local ---
    DIRETORIO_BLAST = os.environ.get(
        "DIRETORIO_BLAST",
        "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/blast_dbs"
    )
    try:
        indices = [f.split('.')[0] for f in os.listdir(DIRETORIO_BLAST) if f.endswith('.nsq') or f.endswith('.00.nsq')]
        bancos_locais_unicos = set([os.path.join(DIRETORIO_BLAST, b) for b in indices])
        string_banco_completo = " ".join(bancos_locais_unicos)
    except FileNotFoundError:
        string_banco_completo = ""
        
    # Mapeamento dinâmico EXCLUSIVO para agrupar os Protozoários
    tags_protozoarios = ["amoebozoa", "sar", "discoba", "metamonada"]
    bancos_protozoa = [os.path.join(DIRETORIO_BLAST, b) for b in tags_protozoarios]
    string_protozoa_completo = " ".join(bancos_protozoa)
    
    # Dicionário: "nome_no_forms": ("arquivo_fasta", "total_estimado_para_cobertura")
    BANCOS_DISPONIVEIS = {
        "fungi": ("fungi_all.fasta", 500000),
        "protozoa": (string_protozoa_completo, 784),
        "bacteria": (os.path.join(DIRETORIO_BLAST, "bacteria"), 22550),
        "archaea": (os.path.join(DIRETORIO_BLAST, "archaea"), 822),
        "nematoda": (os.path.join(DIRETORIO_BLAST, "nematoda"), 248),
        "tardigrada": (os.path.join(DIRETORIO_BLAST, "tardigrada"), 6),
        "rotifera": (os.path.join(DIRETORIO_BLAST, "rotifera"), 20),
        "acari": (os.path.join(DIRETORIO_BLAST, "acari"), 145),
        "collembola": (os.path.join(DIRETORIO_BLAST, "collembola"), 139),
        "minhocas": (os.path.join(DIRETORIO_BLAST, "oligochaeta"), 25),
        "formigas": (os.path.join(DIRETORIO_BLAST, "formicidae"), 213),
        "isopodes": (os.path.join(DIRETORIO_BLAST, "isopoda"), 14),
        "miriapodes": (os.path.join(DIRETORIO_BLAST, "myriapoda"), 68),
        "enchytraeidae": (os.path.join(DIRETORIO_BLAST, "enchytraeidae"), 8),
        "isoptera": (os.path.join(DIRETORIO_BLAST, "isoptera"), 50),
        "platelmintos": (os.path.join(DIRETORIO_BLAST, "platyhelminthes"), 103),
        "amoebozoa": (os.path.join(DIRETORIO_BLAST, "amoebozoa"), 51),
        "sar": (os.path.join(DIRETORIO_BLAST, "sar"), 599),
        "discoba": (os.path.join(DIRETORIO_BLAST, "discoba"), 111),
        "metamonada": (os.path.join(DIRETORIO_BLAST, "metamonada"), 23),
        "refseqsoil": (string_banco_completo, 46190)
    }

    # 1. Busca no dicionário
    if banco_selecionado in BANCOS_DISPONIVEIS:
        arquivo_alvo, total_sequencias_banco = BANCOS_DISPONIVEIS[banco_selecionado]
    else:
        # Fallback de segurança: Se digitar errado, roda contra o Atlas completo
        print(f"⚠️ Banco '{banco_selecionado}' não mapeado. Usando o banco completo 'refseqsoil' por segurança.")
        arquivo_alvo, total_sequencias_banco = BANCOS_DISPONIVEIS["refseqsoil"]
        banco_selecionado = "refseqsoil" # Atualiza o nome para o log do HTML ficar correto

    # 2. Resolução do caminho (Lógica Híbrida)
    if " " in arquivo_alvo or arquivo_alvo.startswith("/"):
        caminho_genomas = arquivo_alvo  
    else:
        # Lógica legada para arquivos .fasta soltos (ex: "fungi_all.fasta")
        caminho_genomas = os.path.join(raiz_projeto, "data/refseq", arquivo_alvo)

    prefixo_saida = os.path.join(pasta_resultado, "saida")
    
    
    cmd_blast = [
        sys.executable, "primer_blast_local.py",
        "-g", caminho_genomas, "-p", caminho_primer, "-o", prefixo_saida,
        "-e", e_value, "--min_size", min_size, "--max_size", max_size,
        "-m", tm_min, "--max_3prime_mismatches", str(mismatches),
        "--qcov_hsp_perc", cobertura, "--max_target_seqs", max_hits,
        "-t", "8",
        "--amp_seq"
    ]
    
    print(f"\n🔍 Rodando BLAST ({req_id})...")
    print("🤖 Comando exato que o Script montou:")
    print(" ".join(cmd_blast))
    print("-" * 50)
	
    print("\n🕵️‍♂️ RAIO-X DA PLANILHA (O que o Python realmente está lendo):")
    for chave, valor in req.items():
        print(f"Coluna: '{chave}' | Valor recebido: '{valor}'")
    print("⚙️ Rodando programa...")
    
    # 1. Inicia o cronômetro
    inicio_blast = time.time() 
    
    try:
        subprocess.run(cmd_blast, cwd=raiz_projeto, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"\n🔥 primer_blast_local.py falhou (exit code {e.returncode}). Saída do processo:")
        print("--- STDOUT ---")
        print(e.stdout or "(vazio)")
        print("--- STDERR ---")
        print(e.stderr or "(vazio)")
        raise
    
    # 2. Para o cronômetro e calcula a diferença
    fim_blast = time.time() 
    tempo_total_segundos = fim_blast - inicio_blast
    
    # 3. Formata o tempo para ficar bonito no log (ex: 1m 45s)
    minutos = int(tempo_total_segundos // 60)
    segundos = int(tempo_total_segundos % 60)
    tempo_formatado = f"{minutos}m {segundos}s"
    
    print(f"⏱️ Tempo de execução do banco '{banco_selecionado}': {tempo_formatado}")

    hits_data_map = {}
    arquivo_pass = f"{prefixo_saida}__results.pass.csv"
    total_matches = 0
    soma_amplicon = 0
    bacterias_encontradas = set()
    
    if os.path.exists(arquivo_pass):
        with open(arquivo_pass, mode='r', encoding='utf-8') as f:
            leitor = csv.DictReader(f)
            for linha in leitor:
                total_matches += 1
                sid = linha.get('Subject_ID', 'Desconhecido')
                bacterias_encontradas.add(sid)
                
                size_val = extrair_campo_flexivel(linha, "size", "0")
                try: soma_amplicon += int(size_val)
                except: pass
                
                if sid not in hits_data_map:
                    hits_data_map[sid] = []
                
                partes_sid = sid.split('|')
                acc_limpo = partes_sid[1] if len(partes_sid) > 1 and partes_sid[0].lower() in ['gb', 'ref', 'emb', 'dbj', 'gi'] else partes_sid[0]
                acc_limpo = acc_limpo.split('.')[0]

                tm_real = "N/A"
                for chave, valor in linha.items():
                    if chave and "amplicon_tm" in chave.lower().strip():
                        tm_real = valor
                        break
        
                hits_data_map[sid].append({
                    "acc": acc_limpo,
                    "size": extrair_campo_flexivel(linha, "size", "N/A"),
                    "tm": tm_real,  # <-- Agora usa o valor cravado!
                    "start": extrair_campo_flexivel(linha, "start", "N/A"),
                    "end": extrair_campo_flexivel(linha, "end", "N/A"),
                    # Tenta pegar as colunas exatas do amplicon primeiro!
                    "seq": linha.get('Amplicon_sequence', linha.get('amplicon_sequence', 'Sequência indisponível'))
                })

    media_amplicon = (soma_amplicon / total_matches) if total_matches > 0 else 0
    lista_bacterias = list(bacterias_encontradas)
    
    print("⚙️ Preparando montagem taxonômica...")
    arvore_real, meta_dict, papeis_funcionais = construir_arvore_aninhada(lista_bacterias, total_matches, hits_data_map, total_sequencias_banco)

    avisos = []
    cobertura_global = (len(lista_bacterias) / total_sequencias_banco) if total_sequencias_banco > 0 else 0
    if cobertura_global < 0.60: avisos.append("Cobertura geral baixa. Verifique os filos relevantes.")
    if mismatches > 2: avisos.append("Potenciais off-targets (Tolerância a mismatch alta).")

    data_bonita = datetime.now().strftime("%d/%m/%Y às %H:%M")

    resultado_json = {
        "request_id": req_id,
        "metadata": {
            "submitted_by": str(req.get('Nome completo', 'Pesquisador')),
            "email": str(req.get('Email', '')), 
            "submitted_at": data_bonita,
            "target_region": str(req.get('Região alvo', 'Não informada')),
            "organism": str(req.get('Tipo de organismo', 'Não informado')),
            "max_mismatches": mismatches,
            "amplicon_min": int(min_size),
            "amplicon_max": int(max_size),
            "e_value": float(e_value),
            "min_coverage": int(cobertura),
            "max_hits": int(max_hits),
            "min_tm": float(tm_min),
            "database": banco_selecionado
        },
        "primers": {
            "forward": fwd,
            "reverse": rev,
            "pair_name": nome_par
        },
        "summary": {
            "total_sequences_checked": total_sequencias_banco,
            "total_matches": len(lista_bacterias),
            "estimated_coverage": round(cobertura_global, 5),
            "off_target_matches": 0,
            "mean_amplicon_size": round(media_amplicon, 1)
        },
        # ---> 2. INJETAR O NOVO NÓ AQUI ANTES DO WARNINGS:
        "functional_tree": papeis_funcionais,
        "taxonomy_tree": arvore_real,
        "leaf_metadata": meta_dict,
        "warnings": avisos
    }

    print("📝 Salvando arquivos de saída (JSON/HTML)...")
    with open(os.path.join(pasta_resultado, "result.json"), 'w', encoding='utf-8') as f:
        json.dump(resultado_json, f, indent=4, ensure_ascii=False)

    shutil.copy(os.path.join(raiz_projeto, "docs/template.html"), os.path.join(pasta_resultado, "index.html"))
    return f"docs/reports/{req_id}", resultado_json

print("\n✅ SCRIPT ONLINE - Monitorando Planilha...")
try:
    cabecalhos = planilha.row_values(1)
    COL_STATUS = cabecalhos.index('Status') + 1
    COL_LINK = cabecalhos.index('Result_path') + 1
except ValueError:
    print("❌ Erro fatal: Colunas Status ou Result_path não encontradas.")
    sys.exit()

while True:
    try:
        registros = planilha.get_all_records()
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
                planilha.update_cell(linha_planilha, COL_STATUS, 'running') 
                
                hoje_str = datetime.now().strftime('%Y%m%d')
                req_id = f"REQ-{hoje_str}-{linha_planilha:04d}"
                
                caminho_relatorio, resultado_json = run_pipeline(req, req_id)

                atualizar_vitrine_html(req, req_id, resultado_json)
                
                planilha.update_cell(linha_planilha, COL_LINK, caminho_relatorio) 
                planilha.update_cell(linha_planilha, COL_STATUS, 'completed')
                
                publicar_no_github(req_id)
                
                email_usuario = str(req.get('Email', '')).strip()
                enviar_email_notificacao(email_usuario, req_id)
                
                print("✨ Processamento da linha concluído com sucesso. Aguardando próximas...")
                    
        time.sleep(10)
    except Exception as e:
        print(f"\n🔥 ERRO FATAL DETECTADO NA EXECUÇÃO PRINCIPAL:")
        traceback.print_exc()
        print("Reiniciando a varredura em 10 segundos...")
        time.sleep(10)
