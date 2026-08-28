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
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import traceback
from dotenv import load_dotenv

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
# MOTOR DE CLASSIFICAÇÃO ECOLÓGICA (Atlas)
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
    ("Aracnídeos (Aranhas e Escorpiões)", "Macrofauna", "Micropredadores", ["araneae", "pseudoscorpiones", "scorpiones", "opiliones"]),
    ("Platelmintos", "Macrofauna", "Micropredadores", ["platyhelminthes", "turbellaria", "geoplanidae"]),
    ("Protistas", "Microfauna", "Micropredadores", ["amoebozoa", "alveolata", "ciliophora", "euglenozoa", "cercozoa", "apicomplexa", "heterolobosea", "foraminifera", "rhizaria", "stramenopiles", "protista"]),
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

# ==========================================
# FUNÇÕES DE APOIO E E-MAIL
# ==========================================
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
    link_pages = f"https://{REPO_OWNER}.github.io/{REPO_NAME}/reports/{req_id}/"
    msg = MIMEMultipart()
    msg['From'] = EMAIL_REMETENTE
    msg['To'] = email_destino
    msg['Subject'] = f"🧬 Análise in silico Concluída ({req_id})"
    corpo = f"Olá,\n\nSua simulação de PCR foi concluída com sucesso!\nID: {req_id}\n\nAcesse o relatório: {link_pages}\n\n⚠️ Aviso Importante: O servidor web leva de 1 a 2 minutos para realizar a publicação dos arquivos. Se você acessar o link e esbarrar em um 'Erro 404' (Página não encontrada), não se preocupe! Aguarde alguns instantes e atualize a página (Ctrl + F5).\n\nAtt,\nEquipe de Bioinformática"
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

# ==========================================
# FUNÇÕES DE TAXONOMIA E GITHUB PAGES
# ==========================================
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
    for coluna, valor in dicionario_linha.items():
        if coluna and palavra_chave.lower() in coluna.lower():
            return valor
    return padrao

def construir_arvore_aninhada(lista_ids, total_matches, hits_data_map):
    total_organismos = len(lista_ids)
    print(f"🌳 Consultando NCBI para {total_organismos} organismos únicos...")
    paths = []
    meta_dict = {} 
    
    functional_roles = {funcao: {} for funcao in FUNCOES_ECOLOGICAS}

    for index, subject_id in enumerate(lista_ids, 1):
        print(f"   ⏳ Classificando [{index}/{total_organismos}]: {subject_id}...", end="\r")
        try:
            # Mesmo tratamento do main.py: pega o campo certo em formatos
            # tipo "gb|JBAMJC...|" (senão pegaria "gb" como se fosse o ID).
            partes = subject_id.split('|')
            acc = partes[1] if len(partes) > 1 and partes[0].lower() in ['gb', 'ref', 'emb', 'dbj', 'gi'] else partes[0]
            acc = acc.split('.')[0]  # Remove a versão do Accession (.1)

            # 1ª tentativa: manifesto local (accession -> taxId), gerado por
            # scripts_auxiliares/gerar_manifesto_taxid.py -- não consulta o
            # NCBI pela rede, é instantâneo. Só cai pro Entrez (mais lento,
            # com limite de taxa) se a sequência não estiver mapeada
            # localmente (ex: banco novo, ainda sem manifesto gerado).
            taxid = taxonomia_local.taxid_por_accession(acc)
            if taxid:
                linhagem = taxonomia_local.linhagem_por_taxid(taxid)
                if not linhagem:
                    raise ValueError("taxId sem linhagem na base de taxonomia local")
                if linhagem[0].lower() == "cellular organisms":
                    linhagem.pop(0)
                especie = linhagem[-1]
                acc_final = acc
                desc_final = "Descrição indisponível"
                length_final = "N/A"
            else:
                handle = Entrez.efetch(db="nucleotide", id=acc, retmode="xml")
                records = Entrez.read(handle)
                handle.close()
                if not records:
                    raise ValueError("Sequência não encontrada no NCBI")
                rec = records[0]
                linhagem = rec["GBSeq_taxonomy"].split("; ")
                especie = rec["GBSeq_organism"]
                linhagem.append(especie)
                if linhagem[0].lower() == "cellular organisms":
                    linhagem.pop(0)
                acc_final = rec.get("GBSeq_primary-accession", acc)
                desc_final = rec.get("GBSeq_definition", "Descrição indisponível")
                length_final = rec.get("GBSeq_length", "N/A")
                time.sleep(0.4)  # só precisa respeitar o limite de taxa do NCBI no fallback

            paths.append(linhagem)

            if especie not in meta_dict:
                meta_dict[especie] = {
                    "info": {
                        "acc": acc_final,
                        "desc": desc_final,
                        "length": length_final
                    },
                    "amplicons": []
                }

            grupo, tamanho, funcao = classificar_ecologia(linhagem)

            if grupo not in functional_roles[funcao]:
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
    raiz_projeto = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    try:
        subprocess.run(["git", "add", "docs/"], cwd=raiz_projeto, check=True, stdout=subprocess.DEVNULL)
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

# ==========================================
# MOTOR PRINCIPAL (RUN PIPELINE)
# ==========================================
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
    # Mesmo motor usado no main.py (Google Sheets) — aqui a única
    # diferença é a origem da requisição (GitHub Issues em vez de Sheets).
    # ==========================================
    banco_selecionado = str(req.get('Banco de Dados', 'refseqsoil')).strip().lower()

    # --- Mapeamento Dinâmico do Banco Completo Local ---
    DIRETORIO_BLAST = os.environ.get(
        "DIRETORIO_BLAST",
        "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/blast_dbs"
    )
    try:
        indices = [f.split('.')[0] for f in os.listdir(DIRETORIO_BLAST) if f.endswith('.nsq') or f.endswith('.00.nsq')]
        bancos_locais_unicos = sorted(set(indices))
        string_banco_completo = " ".join(os.path.join(DIRETORIO_BLAST, b) for b in bancos_locais_unicos)
    except FileNotFoundError:
        bancos_locais_unicos = []
        string_banco_completo = ""

    # Mapeamento dinâmico EXCLUSIVO para agrupar os Protozoários
    tags_protozoarios = ["amoebozoa", "sar", "discoba", "metamonada"]
    bancos_protozoa = [os.path.join(DIRETORIO_BLAST, b) for b in tags_protozoarios]
    string_protozoa_completo = " ".join(bancos_protozoa)

    # Mapeamento dinâmico EXCLUSIVO para agrupar os Fungos: os 6 filos que o
    # motor de classificação ecológica (classificar_ecologia) já reconhece
    # como "Fungos" -- quando o usuário escolhe "Fungi" no formulário, roda
    # contra os 6 juntos, igual ao grupo "protozoa" acima.
    tags_fungos = [
        "basidiomycota", "ascomycota", "mucoromycota",
        "chytridiomycota", "zoopagomycota", "glomeromycota",
    ]
    bancos_fungos = [os.path.join(DIRETORIO_BLAST, b) for b in tags_fungos]
    string_fungos_completo = " ".join(bancos_fungos)

    # Mapeamento dinâmico EXCLUSIVO para agrupar as Minhocas: oligochaeta
    # (minhocas propriamente ditas) + enchytraeidae (minhocas-brancas,
    # parentes menores da mesma classe Clitellata) -- não existe opção
    # separada de "Enchytraeidae" no formulário, então "Minhocas" cobre as duas.
    tags_minhocas = ["oligochaeta", "enchytraeidae"]
    bancos_minhocas = [os.path.join(DIRETORIO_BLAST, b) for b in tags_minhocas]
    string_minhocas_completo = " ".join(bancos_minhocas)

    # Banco "eucariotos": igual ao refseqsoil completo, mas sem bacteria/
    # archaea. Ver comentário equivalente em main.py.
    tags_nao_eucariotos = {"bacteria", "archaea"}
    bancos_eucariotos = [b for b in bancos_locais_unicos if b not in tags_nao_eucariotos]
    string_eucariotos_completo = " ".join(os.path.join(DIRETORIO_BLAST, b) for b in bancos_eucariotos)

    # Contagem REAL de genomas/organismos por grupo, lida do manifesto gerado
    # por scripts_auxiliares/gerar_manifesto_taxid.py (a partir dos
    # assembly_data_report.jsonl reais). Substitui os números fixos que
    # existiam aqui antes -- eles tinham ficado desatualizados: a soma dos
    # 18 grupos individuais (25.195) nem batia com o total combinado do
    # "refseqsoil" (46.190) que deveriam somar. Só cai pro número antigo,
    # abaixo, se o manifesto daquele grupo específico ainda não existir.
    VALORES_ANTIGOS_FALLBACK = {
        "bacteria": 22550, "archaea": 822, "nematoda": 248, "tardigrada": 6,
        "rotifera": 20, "acari": 145, "collembola": 139, "oligochaeta": 25,
        "formicidae": 213, "isopoda": 14, "myriapoda": 68, "enchytraeidae": 8,
        "isoptera": 50, "platyhelminthes": 103, "amoebozoa": 51, "sar": 599,
        "discoba": 111, "metamonada": 23,
    }

    def _contagem_real(grupo_taxid):
        real = taxonomia_local.contagem_organismos_grupo(grupo_taxid)
        return real if real is not None else VALORES_ANTIGOS_FALLBACK.get(grupo_taxid, 0)

    total_protozoa = sum(_contagem_real(g) for g in tags_protozoarios)
    total_fungos = sum(_contagem_real(g) for g in tags_fungos)
    total_minhocas = sum(_contagem_real(g) for g in tags_minhocas)
    total_refseqsoil = sum(_contagem_real(g) for g in bancos_locais_unicos)
    total_eucariotos = sum(_contagem_real(g) for g in bancos_eucariotos)

    # Dicionário: "nome_no_forms/issue": ("arquivo_fasta", "total_real_de_organismos")
    BANCOS_DISPONIVEIS = {
        "fungi": (string_fungos_completo, total_fungos),
        "protozoa": (string_protozoa_completo, total_protozoa),
        "eucariotos": (string_eucariotos_completo, total_eucariotos),
        "bacteria": (os.path.join(DIRETORIO_BLAST, "bacteria"), _contagem_real("bacteria")),
        "archaea": (os.path.join(DIRETORIO_BLAST, "archaea"), _contagem_real("archaea")),
        "nematoda": (os.path.join(DIRETORIO_BLAST, "nematoda"), _contagem_real("nematoda")),
        "tardigrada": (os.path.join(DIRETORIO_BLAST, "tardigrada"), _contagem_real("tardigrada")),
        "rotifera": (os.path.join(DIRETORIO_BLAST, "rotifera"), _contagem_real("rotifera")),
        "acari": (os.path.join(DIRETORIO_BLAST, "acari"), _contagem_real("acari")),
        "collembola": (os.path.join(DIRETORIO_BLAST, "collembola"), _contagem_real("collembola")),
        "minhocas": (string_minhocas_completo, total_minhocas),
        "formigas": (os.path.join(DIRETORIO_BLAST, "formicidae"), _contagem_real("formicidae")),
        "isopodes": (os.path.join(DIRETORIO_BLAST, "isopoda"), _contagem_real("isopoda")),
        "miriapodes": (os.path.join(DIRETORIO_BLAST, "myriapoda"), _contagem_real("myriapoda")),
        "enchytraeidae": (os.path.join(DIRETORIO_BLAST, "enchytraeidae"), _contagem_real("enchytraeidae")),
        "isoptera": (os.path.join(DIRETORIO_BLAST, "isoptera"), _contagem_real("isoptera")),
        "cupins": (os.path.join(DIRETORIO_BLAST, "isoptera"), _contagem_real("isoptera")),  # alias -- dropdown do Issue usa "Cupins", não "Isoptera"
        "platelmintos": (os.path.join(DIRETORIO_BLAST, "platyhelminthes"), _contagem_real("platyhelminthes")),
        "amoebozoa": (os.path.join(DIRETORIO_BLAST, "amoebozoa"), _contagem_real("amoebozoa")),
        "sar": (os.path.join(DIRETORIO_BLAST, "sar"), _contagem_real("sar")),
        "discoba": (os.path.join(DIRETORIO_BLAST, "discoba"), _contagem_real("discoba")),
        "metamonada": (os.path.join(DIRETORIO_BLAST, "metamonada"), _contagem_real("metamonada")),
        "basidiomycota": (os.path.join(DIRETORIO_BLAST, "basidiomycota"), _contagem_real("basidiomycota")),
        "ascomycota": (os.path.join(DIRETORIO_BLAST, "ascomycota"), _contagem_real("ascomycota")),
        "mucoromycota": (os.path.join(DIRETORIO_BLAST, "mucoromycota"), _contagem_real("mucoromycota")),
        "chytridiomycota": (os.path.join(DIRETORIO_BLAST, "chytridiomycota"), _contagem_real("chytridiomycota")),
        "zoopagomycota": (os.path.join(DIRETORIO_BLAST, "zoopagomycota"), _contagem_real("zoopagomycota")),
        "glomeromycota": (os.path.join(DIRETORIO_BLAST, "glomeromycota"), _contagem_real("glomeromycota")),
        "refseqsoil": (string_banco_completo, total_refseqsoil)
    }

    # 1. Busca no dicionário
    if banco_selecionado in BANCOS_DISPONIVEIS:
        arquivo_alvo, total_sequencias_banco = BANCOS_DISPONIVEIS[banco_selecionado]
    else:
        # Fallback de segurança: Se digitar errado, roda contra o Atlas completo
        print(f"⚠️ Banco '{banco_selecionado}' não mapeado. Usando o banco completo 'refseqsoil' por segurança.")
        arquivo_alvo, total_sequencias_banco = BANCOS_DISPONIVEIS["refseqsoil"]
        banco_selecionado = "refseqsoil"  # Atualiza o nome para o log/JSON ficar correto

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
    
    print(f"\n🔍 Rodando BLAST ({req_id}) no banco {banco_selecionado}...")
    print("🤖 Comando exato que o Script montou:")
    print(" ".join(cmd_blast))
    print("-" * 50)
    
    print("\n🕵️‍♂️ RAIO-X DA ISSUE (O que o Python realmente está lendo):")
    for chave, valor in req.items():
        print(f"Coluna: '{chave}' | Valor recebido: '{valor}'")
    print("⚙️ Rodando programa...")

    inicio_blast = time.time()
    subprocess.run(cmd_blast, cwd=raiz_projeto, check=True, capture_output=True, text=True)
    fim_blast = time.time()

    tempo_total_segundos = fim_blast - inicio_blast
    minutos = int(tempo_total_segundos // 60)
    segundos = int(tempo_total_segundos % 60)
    print(f"⏱️ Tempo de execução do banco '{banco_selecionado}': {minutos}m {segundos}s")

    hits_data_map = {}
    arquivo_pass = f"{prefixo_saida}__results.pass.csv"
    total_matches = 0
    soma_amplicon = 0
    bacterias_encontradas = set()

    # Limite global (não por espécie) de caracteres de sequência de amplicon
    # guardados no result.json. Sem isso, buscas com muitos hits geram um
    # JSON gigante -- já aconteceu de passar dos 145MB, estourando o limite
    # de 100MB por arquivo do GitHub e travando o push do relatório. O corte
    # é só na sequência (o resto do hit -- acc/size/tm/start/end -- continua
    # sendo salvo pra TODOS os hits, então nenhuma estatística é perdida, só
    # deixa de ter a sequência completa pros hits além do orçamento).
    ORCAMENTO_MAX_CARACTERES_SEQ = 15_000_000
    caracteres_seq_acumulados = 0

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

                seq_amplicon = linha.get('Amplicon_sequence', linha.get('amplicon_sequence', 'Sequência indisponível'))
                if caracteres_seq_acumulados < ORCAMENTO_MAX_CARACTERES_SEQ:
                    caracteres_seq_acumulados += len(seq_amplicon)
                else:
                    seq_amplicon = "Sequência omitida (limite de tamanho do relatório atingido) — dados brutos disponíveis no servidor."

                hits_data_map[sid].append({
                    "acc": acc_limpo,
                    "size": extrair_campo_flexivel(linha, "size", "N/A"),
                    "tm": tm_real,
                    "start": extrair_campo_flexivel(linha, "start", "N/A"),
                    "end": extrair_campo_flexivel(linha, "end", "N/A"),
                    "seq": seq_amplicon
                })

    media_amplicon = (soma_amplicon / total_matches) if total_matches > 0 else 0
    lista_bacterias = list(bacterias_encontradas)
    
    print("⚙️ Preparando montagem taxonômica...")
    arvore_real, meta_dict, papeis_funcionais = construir_arvore_aninhada(lista_bacterias, total_matches, hits_data_map)

    avisos = []
    # Cobertura = organismos ÚNICOS batidos (len(meta_dict), 1 por espécie)
    # sobre o total de organismos do grupo -- NÃO len(lista_bacterias), que
    # conta SEQUÊNCIAS (scaffolds/contigs individuais, várias por organismo
    # em genomas fragmentados). Ver comentário equivalente em main.py.
    total_organismos_unicos = len(meta_dict)
    cobertura_global = (total_organismos_unicos / total_sequencias_banco) if total_sequencias_banco > 0 else 0
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
            "unique_organisms": total_organismos_unicos,
            "estimated_coverage": round(cobertura_global, 5),
            "off_target_matches": 0,
            "mean_amplicon_size": round(media_amplicon, 1)
        },
        "functional_tree": papeis_funcionais,
        "taxonomy_tree": arvore_real,
        "leaf_metadata": meta_dict,
        "warnings": avisos
    }

    print("📝 Salvando arquivos de saída (JSON/HTML)...")
    with open(os.path.join(pasta_resultado, "result.json"), 'w', encoding='utf-8') as f:
        # Sem indent: ver comentário equivalente em main.py.
        json.dump(resultado_json, f, ensure_ascii=False, separators=(',', ':'))

    shutil.copy(os.path.join(raiz_projeto, "docs/template.html"), os.path.join(pasta_resultado, "index.html"))
    return f"docs/reports/{req_id}", resultado_json

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

def atualizar_status_issue(numero_issue, req_id):
    url_comments = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues/{numero_issue}/comments"
    link_pages = f"https://{REPO_OWNER}.github.io/{REPO_NAME}/reports/{req_id}/"
    
    corpo_comentario = {
        "body": f"✅ **Análise in silico concluída com sucesso!**\n\nO pipeline do laboratório processou seus primers. O relatório interativo com a árvore taxonômica e a cobertura já está disponível.\n\n👉 **[Acessar Relatório Completo]({link_pages})**\n\n> ⚠️ **Aviso Importante:** O servidor do GitHub Pages leva de 1 a 2 minutos para concluir o deploy. Se você clicar no link agora e ver uma tela de **Erro 404** (Page not found) ou a página em branco, aguarde alguns instantes e force a atualização da página (`F5` ou `Ctrl + F5`)."
    }
    requests.post(url_comments, headers=HEADERS, json=corpo_comentario)

    url_issue = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues/{numero_issue}"
    modificacoes = {
        "state": "closed",
        "labels": ["analise-concluida"]
    }
    requests.patch(url_issue, headers=HEADERS, json=modificacoes)

def parse_issue_body(body):
    sections = re.split(r'###\s+', body)
    data = {}
    for sec in sections:
        if not sec.strip(): continue
        lines = sec.strip().split('\n')
        key = lines[0].strip()
        value = '\n'.join(lines[1:]).strip()
        if value == "_No response_": value = ""
        data[key] = value
    
    req = {
        'Nome completo': data.get('Nome do Pesquisador', 'Pesquisador'),
        'Email': data.get('E-mail para Notificação', ''),
        'Nome do Par de Primers': data.get('Nome do Par de Primers', ''),
        'Primer forward': data.get("Primer Forward (5' -> 3')", ''),
        'Primer reverse': data.get("Primer Reverse (5' -> 3')", ''),
        'Região alvo': data.get('Região Alvo', '18S'),
        'Banco de Dados': data.get('Banco de Dados', 'Protozoa'),
        'Tipo de organismo': data.get('Tipo de organismo', 'Eukaryota'),
        'Máximo de Mismatches na extremidade 3': data.get("Máximo de Mismatches (Extremidade 3')", '3'),
        'Tamanho do amplicon: MIN': data.get('Tamanho Mínimo do Amplicon (bp)', '3000'),
        'Tamanho do amplicon: MAX': data.get('Tamanho Máximo do Amplicon (bp)', '8000'),
        'Temperatura de Melting mínima (Tm)': data.get('Temperatura de Melting mínima (Tm)', '0'),
        'E-value máximo': data.get('E-value Máximo', '10'),
        'Cobertura mínima': data.get('Cobertura mínima (%)', '70'),
        'Limite de hits': data.get('Limite de hits', '500')
    }
    return req

# ==========================================
# LOOP PRINCIPAL DO MOTOR GITHUB ISSUES
# ==========================================
print("\n✅ SCRIPT HÍBRIDO ONLINE - Monitorando GitHub Issues...")

while True:
    try:
        issues = buscar_requisicoes_github()
        for issue in issues:
            numero_issue = issue['number']
            corpo = issue['body']
            
            print(f"\n🔔 Nova requisição encontrada na Issue #{numero_issue}!")
            
            url_issue = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues/{numero_issue}"
            requests.patch(url_issue, headers=HEADERS, json={"labels": ["running"]})

            req_mapeado = parse_issue_body(corpo)
            
            hoje_str = datetime.now().strftime('%Y%m%d')
            req_id = f"REQ-{hoje_str}-ISSUE{numero_issue:04d}"
            
            caminho_relatorio, resultado_json = run_pipeline(req_mapeado, req_id)
            atualizar_vitrine_html(req_mapeado, req_id, resultado_json)
            publicar_no_github(req_id)
            
            email_usuario = req_mapeado.get('Email', '')
            enviar_email_notificacao(email_usuario, req_id)
            
            atualizar_status_issue(numero_issue, req_id)
            
            print(f"✨ Issue #{numero_issue} finalizada com sucesso! Aguardando próximas...")
            
        time.sleep(15)
        
    except Exception as e:
        print(f"\n🔥 ERRO NA VARREDURA DE ISSUES: {e}")
        time.sleep(15)
