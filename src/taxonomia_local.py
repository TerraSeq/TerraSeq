"""
Resolve a classificacao taxonomica (linhagem completa) de uma sequencia de
forma 100% local, sem consultar o NCBI pela rede.

Antes, construir_arvore_aninhada() em main.py fazia uma chamada Entrez.efetch
por organismo (+ sleep de 0.4s pra respeitar o limite de taxa do NCBI), o que
tornava essa etapa o maior gargalo de tempo do pipeline pra buscas com muitos
organismos unicos. Este modulo substitui isso por duas fontes 100% locais:

1. Um manifesto accession -> taxId em SQLite (gerado uma vez por
   scripts_auxiliares/gerar_manifesto_taxid.py, cruzando os
   assembly_data_report.jsonl do NCBI Datasets com os cabecalhos dos .fna
   ja baixados). Usamos SQLite (indice em disco) em vez de um dicionario
   Python carregado inteiro na memoria porque os bancos combinados de vocês
   passam de 90 milhoes de sequencias -- um dict desse tamanho facilmente
   estoura dezenas de GB de RAM sozinho (o mesmo tipo de problema que
   causou os OOM kills corrigidos em run_parse_blastn.py). Com SQLite, a
   busca por accession usa o indice da PRIMARY KEY e fica praticamente
   instantanea, com uso de memoria desprezivel.
2. A base de taxonomia oficial do NCBI (taxdump: nodes.dmp + names.dmp),
   baixada uma unica vez e usada pra montar a linhagem completa de qualquer
   taxId apenas subindo a arvore de pais em memoria -- sem rede. Essa parte
   SIM cabe tranquilamente em memoria: a taxonomia inteira do NCBI tem só
   ~2-3 milhoes de taxons, não centenas de milhões de sequências.

main.py so cai de volta pro Entrez.efetch quando uma sequencia nao esta
mapeada no manifesto local (ex: banco novo, ainda sem manifesto gerado).
"""
import json
import os
import sqlite3
import tarfile
import urllib.request

DIRETORIO_DADOS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
DIRETORIO_TAXDUMP = os.path.join(DIRETORIO_DADOS, "taxdump")
DIRETORIO_MANIFESTOS = os.path.join(DIRETORIO_DADOS, "manifestos")
CAMINHO_DB_MANIFESTO = os.path.join(DIRETORIO_MANIFESTOS, "taxid.sqlite")
CAMINHO_CONTAGEM_ORGANISMOS = os.path.join(DIRETORIO_MANIFESTOS, "contagem_organismos.json")
URL_TAXDUMP = "https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdump.tar.gz"

_taxid_para_pai = None
_taxid_para_nome = None
_conexao_manifesto = None
_contagem_organismos = None


def _baixar_taxdump_se_necessario():
    nodes_path = os.path.join(DIRETORIO_TAXDUMP, "nodes.dmp")
    names_path = os.path.join(DIRETORIO_TAXDUMP, "names.dmp")
    if os.path.exists(nodes_path) and os.path.exists(names_path):
        return
    os.makedirs(DIRETORIO_TAXDUMP, exist_ok=True)
    tar_path = os.path.join(DIRETORIO_TAXDUMP, "taxdump.tar.gz")
    print("🌐 Baixando base de taxonomia do NCBI (~500MB, feito só uma vez)...")
    urllib.request.urlretrieve(URL_TAXDUMP, tar_path)
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(DIRETORIO_TAXDUMP, filter="data")
    os.remove(tar_path)
    print("✅ Base de taxonomia local pronta.")


def _carregar_taxdump():
    global _taxid_para_pai, _taxid_para_nome
    if _taxid_para_pai is not None:
        return
    _baixar_taxdump_se_necessario()

    _taxid_para_pai = {}
    with open(os.path.join(DIRETORIO_TAXDUMP, "nodes.dmp"), "r", encoding="utf-8", errors="ignore") as f:
        for linha in f:
            campos = [c.strip() for c in linha.split("|")]
            taxid, pai = campos[0], campos[1]
            _taxid_para_pai[taxid] = pai

    _taxid_para_nome = {}
    with open(os.path.join(DIRETORIO_TAXDUMP, "names.dmp"), "r", encoding="utf-8", errors="ignore") as f:
        for linha in f:
            campos = [c.strip() for c in linha.split("|")]
            taxid, nome, classe_nome = campos[0], campos[1], campos[3]
            if classe_nome == "scientific name":
                _taxid_para_nome[taxid] = nome


def linhagem_por_taxid(taxid):
    """Retorna a linhagem completa (lista de nomes, da raiz ate a especie) de
    um taxId, subindo a arvore de pais 100% em memoria."""
    _carregar_taxdump()
    taxid = str(taxid)
    linhagem = []
    visitados = set()
    while taxid in _taxid_para_pai and taxid not in visitados:
        visitados.add(taxid)
        nome = _taxid_para_nome.get(taxid)
        # "root" e um no artificial da arvore do NCBI -- o GBSeq_taxonomy do
        # Entrez nunca inclui ele, entao pulamos aqui pra manter o mesmo
        # formato que o resto do codigo (classificar_ecologia, etc.) espera.
        if nome and nome.lower() != "root":
            linhagem.append(nome)
        pai = _taxid_para_pai[taxid]
        if pai == taxid:
            break
        taxid = pai
    linhagem.reverse()
    return linhagem


def _conectar_manifesto():
    global _conexao_manifesto
    if _conexao_manifesto is not None:
        return _conexao_manifesto
    if not os.path.exists(CAMINHO_DB_MANIFESTO):
        return None
    # uri=True + mode=ro: abre só leitura, várias submissões podem consultar
    # ao mesmo tempo sem disputar lock de escrita com o script de geração.
    _conexao_manifesto = sqlite3.connect(f"file:{CAMINHO_DB_MANIFESTO}?mode=ro", uri=True)
    return _conexao_manifesto


def taxid_por_accession(acc):
    """Busca o taxId de uma sequência no manifesto local (SQLite, busca
    indexada, sem carregar nada em memória). Retorna None se a sequência
    não estiver mapeada (ex: banco baixado depois do último
    gerar_manifesto_taxid.py)."""
    conexao = _conectar_manifesto()
    if conexao is None:
        return None
    linha = conexao.execute("SELECT taxid FROM sequencias WHERE accession = ?", (acc,)).fetchone()
    return linha[0] if linha else None


def _carregar_contagem_organismos():
    global _contagem_organismos
    if _contagem_organismos is not None:
        return
    _contagem_organismos = {}
    if not os.path.exists(CAMINHO_CONTAGEM_ORGANISMOS):
        return
    with open(CAMINHO_CONTAGEM_ORGANISMOS, "r", encoding="utf-8") as f:
        _contagem_organismos = json.load(f)


def contagem_organismos_grupo(grupo):
    """Quantidade real de genomas/organismos baixados pra um grupo (ex:
    "isopoda"), contada a partir do assembly_data_report.jsonl real (não um
    número digitado à mão). Retorna None se o grupo não tiver manifesto
    gerado ainda (main.py cai pro valor antigo, hardcoded, nesse caso)."""
    _carregar_contagem_organismos()
    return _contagem_organismos.get(grupo)
