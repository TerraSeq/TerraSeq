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

# --- CONFIGURAÇÕES INICIAIS ---
Entrez.email = "tiagogabriel3542@gmial.com"

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_REMETENTE = "tiagogabriel3542@gmail.com" 
EMAIL_SENHA = "huyapitnfjegbsuz"

caminho_credenciais = os.path.join(os.path.dirname(__file__), 'credentials.json')
scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_file(caminho_credenciais, scopes=scopes)
client = gspread.authorize(credentials)

NOME_DA_PLANILHA = "Submissoes_Primers_Pipeline"
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
    link_pages = f"https://tiagogabrielsi.github.io/pipeline_genoma/reports/{req_id}/"
    msg = MIMEMultipart()
    msg['From'] = EMAIL_REMETENTE
    msg['To'] = email_destino
    msg['Subject'] = f"🧬 Análise in silico Concluída ({req_id})"
    corpo = f"Olá,\n\nSua simulação de PCR foi concluída com sucesso!\nID: {req_id}\n\nAcesse o relatório: {link_pages}\n\n⚠️ Aviso Importante: O servidor web leva de 1 a 2 minutos para realizar a publicação dos arquivos. Se você acessar o link e esbarrar em um 'Erro 404' (Página não encontrada), não se preocupe! Aguarde alguns instantes e atualize a página (Ctrl + F5).\n\nAtt,\Equipe de Bioinformática"
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

def construir_arvore_aninhada(lista_ids, total_matches, hits_data_map):
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
            acc = subject_id.split('|')[0].split('.')[0] 
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
        
        
def atualizar_vitrine_html(req, req_id):
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
    data_hoje = datetime.now().strftime("%d/%m/%Y")

    marcador_alvo = "<!-- NOVAS_LINHAS -->"

    nova_linha = f"""
                    <tr>
                        <td><strong>{req_id}</strong></td>
                        <td>{alvo}</td>
                        <td>{banco}</td>
                        <td style="font-family: monospace; color: var(--primary-color); line-height: 1.5;">
                            <span style="color: #666; font-weight: 600; font-family: 'Segoe UI', sans-serif;">F:</span> {fwd}<br>
                            <span style="color: #666; font-weight: 600; font-family: 'Segoe UI', sans-serif;">R:</span> {rev}
                        </td>
                        <td>{data_hoje}</td>
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
    # NOVO: SELEÇÃO DINÂMICA DO BANCO DE DADOS (ATLAS)
    # ==========================================
    banco_selecionado = str(req.get('Banco de Dados', 'Protozoa')).strip().lower()
    
    # Dicionário: "nome_no_forms": ("arquivo_fasta", "total_estimado_para_cobertura")
    BANCOS_DISPONIVEIS = {
        "fungi": ("fungi_all.fasta", 500000),
        "protozoa": ("protozoa_all.fasta", 150000),
        "bacteria": ("bacteria_all.fasta", 2000000),
        "archaea": ("archaea_all.fasta", 50000),
        "nematoda": ("nematoda_all.fasta", 30000),
        "tardigrada": ("tardigrada_all.fasta", 500),
        "rotifera": ("rotifera_all.fasta", 1000),
        "acari": ("acari_all.fasta", 10000),
        "collembola": ("collembola_all.fasta", 5000),
        "minhocas": ("minhocas_all.fasta", 2000),
        "formigas": ("formicidae_all.fasta", 15000),
        "cupins": ("termitoidae_all.fasta", 8000),
        "isopodes": ("isopoda_all.fasta", 2000),
        "miriapodes": ("myriapoda_all.fasta", 1500),
        "mistura_teste": ("mistura_solo.fasta", 42000),
        
        # --- NOVOS BANCOS ADICIONADOS ---
        "platelmintos": ("platelmintos_all.fasta", 5000),
        "aracnideos": ("aracnideos_all.fasta", 12000),
        "insetos": ("insetos_all.fasta", 50000),
        "moluscos": ("moluscos_all.fasta", 15000),
        "plantas": ("plantas_all.fasta", 100000),
        "virus": ("virus_all.fasta", 1000000),
        "megafauna": ("megafauna_all.fasta", 50000)
    }

    if banco_selecionado in BANCOS_DISPONIVEIS:
        arquivo_alvo, total_sequencias_banco = BANCOS_DISPONIVEIS[banco_selecionado]
    else:
        # Fallback de segurança se o usuário digitar algo errado
        arquivo_alvo, total_sequencias_banco = ("protozoa_all.fasta", 150000)

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
    subprocess.run(cmd_blast, cwd=raiz_projeto, check=True, capture_output=True, text=True)

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
                
                acc_limpo = sid.split('|')[0].split('.')[0]

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
    arvore_real, meta_dict, papeis_funcionais = construir_arvore_aninhada(lista_bacterias, total_matches, hits_data_map)

    avisos = []
    cobertura_global = (len(lista_bacterias) / 150000) 
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
            "reverse": rev
        },
        "summary": {
            "total_sequences_checked": 150000,
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
    return f"docs/reports/{req_id}"

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
            status_atual = str(req.get('Status', '')).strip().lower()
            
            if status_atual == '' or status_atual == 'pending':
                print(f"\n🔔 Nova requisição encontrada na linha {linha_planilha}!")
                planilha.update_cell(linha_planilha, COL_STATUS, 'running') 
                
                hoje_str = datetime.now().strftime('%Y%m%d')
                req_id = f"REQ-{hoje_str}-{linha_planilha:04d}"
                
                caminho_relatorio = run_pipeline(req, req_id)
                
                atualizar_vitrine_html(req, req_id)
                
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
