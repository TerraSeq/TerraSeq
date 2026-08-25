"""
Resolve a classificacao taxonomica (linhagem completa) de uma sequencia de
forma 100% local, sem consultar o NCBI pela rede.

Antes, construir_arvore_aninhada() em main.py fazia uma chamada Entrez.efetch
por organismo (+ sleep de 0.4s pra respeitar o limite de taxa do NCBI), o que
tornava essa etapa o maior gargalo de tempo do pipeline pra buscas com muitos
organismos unicos. Este modulo substitui isso por duas fontes 100% locais:

1. Um manifesto accession -> taxId (gerado uma vez por
   scripts_auxiliares/gerar_manifesto_taxid.py, cruzando os
   assembly_data_report.jsonl do NCBI Datasets com os cabecalhos dos .fna
   ja baixados).
2. A base de taxonomia oficial do NCBI (taxdump: nodes.dmp + names.dmp),
   baixada uma unica vez e usada pra montar a linhagem completa de qualquer
   taxId apenas subindo a arvore de pais em memoria -- sem rede.

main.py so cai de volta pro Entrez.efetch quando uma sequencia nao esta
mapeada no manifesto local (ex: banco novo, ainda sem manifesto gerado).
"""
import os
import tarfile
import urllib.request

DIRETORIO_DADOS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
DIRETORIO_TAXDUMP = os.path.join(DIRETORIO_DADOS, "taxdump")
DIRETORIO_MANIFESTOS = os.path.join(DIRETORIO_DADOS, "manifestos")
URL_TAXDUMP = "https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdump.tar.gz"

_taxid_para_pai = None
_taxid_para_nome = None
_acc_para_info = None


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


def _carregar_manifestos_taxid():
    global _acc_para_info
    if _acc_para_info is not None:
        return
    _acc_para_info = {}
    if not os.path.isdir(DIRETORIO_MANIFESTOS):
        return
    for nome_arquivo in os.listdir(DIRETORIO_MANIFESTOS):
        if not nome_arquivo.endswith("_taxid.tsv"):
            continue
        with open(os.path.join(DIRETORIO_MANIFESTOS, nome_arquivo), "r", encoding="utf-8", errors="ignore") as f:
            for linha in f:
                partes = linha.rstrip("\n").split("\t")
                if len(partes) < 3:
                    continue
                acc, taxid, organismo = partes[0], partes[1], partes[2]
                descricao = partes[3] if len(partes) > 3 else ""
                _acc_para_info[acc] = (taxid, organismo, descricao)


def info_por_accession(acc):
    """Busca (taxId, nome_organismo, descricao) de uma sequencia no manifesto
    local. Retorna (None, None, None) se a sequencia nao estiver mapeada
    (ex: banco baixado depois do ultimo gerar_manifesto_taxid.py)."""
    _carregar_manifestos_taxid()
    return _acc_para_info.get(acc, (None, None, None))
