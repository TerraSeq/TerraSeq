"""
Os bancos de busca que o formulário oferece: quais grupos do acervo cada um
junta, onde estão os índices BLAST e quantos genomas o banco tem.

Um "grupo" é um banco BLAST indexado em DIRETORIO_BLAST (ex: "formicidae",
"ascomycota"). Um "banco" é o que o pesquisador escolhe no formulário: pode
ser um grupo só ("nematoda"), um apelido ("formigas" -> formicidae) ou vários
grupos juntos ("fungi" -> os 6 filos de fungos).

    import bancos
    banco = bancos.resolver("fungi")        # None se o banco não existir
    banco.caminho_blast, banco.total_genomas, banco.grupos

Os mesmos bancos aparecem também, para o site, em docs/template.html
(GRUPOS_COMPOSTOS) e no formulário (.github/ISSUE_TEMPLATE/solicitacao_analise.yml).
"""
import os
from collections import namedtuple

import taxonomia_local

DIRETORIO_BLAST_PADRAO = "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/blast_dbs"

# Bancos que juntam vários grupos numa busca só (a ordem é a do comando do BLAST).
BANCOS_COMPOSTOS = {
    # Os 4 grandes grupos de protozoários do acervo.
    "protozoa": ["amoebozoa", "sar", "discoba", "metamonada"],
    # Os 6 filos que a classificação ecológica (ecologia.py) reconhece como
    # "Fungos": escolher "Fungi" no formulário roda contra os 6 juntos.
    "fungi": ["basidiomycota", "ascomycota", "mucoromycota", "chytridiomycota", "zoopagomycota", "glomeromycota"],
    # Oligochaeta (minhocas propriamente ditas) + Enchytraeidae (minhocas-brancas,
    # parentes menores da mesma classe Clitellata) -- o formulário não tem opção
    # separada de "Enchytraeidae", então "Minhocas" cobre as duas.
    "minhocas": ["oligochaeta", "enchytraeidae"],
    # Bactérias + arqueias (marcadores 16S).
    "procariotos": ["bacteria", "archaea"],
}

# Bancos de um grupo só cujo nome no formulário é diferente do nome do grupo.
APELIDOS = {
    "formigas": "formicidae",
    "isopodes": "isopoda",
    "miriapodes": "myriapoda",
    "cupins": "isoptera",          # o formulário das Issues usa "Cupins", não "Isoptera"
    "platelmintos": "platyhelminthes",
}

# Bancos de um grupo só, com o mesmo nome do grupo.
GRUPOS_INDIVIDUAIS = [
    "bacteria", "archaea", "nematoda", "tardigrada", "rotifera", "acari", "collembola",
    "enchytraeidae", "isoptera", "coleoptera", "gastropoda", "apoidea", "araneae",
    "scorpiones", "pseudoscorpiones", "amoebozoa", "sar", "discoba", "metamonada",
    "basidiomycota", "ascomycota", "mucoromycota", "chytridiomycota", "zoopagomycota",
    "glomeromycota",
]

# Grupos que NÃO entram no banco "eucariotos". "eucariotos" é o refseqsoil
# completo sem bactérias/arqueias: elas são a maioria do refseqsoil (>90% dos
# organismos), mas não têm a região 18S (gene ribossomal EUCARIÓTICO;
# procarionte usa 16S). Pra um primer 18S/ITS/28S, incluí-las no denominador
# da cobertura inflaria o "total de genomas no banco" com organismos que o
# primer NUNCA poderia amplificar.
GRUPOS_NAO_EUCARIOTOS = {"bacteria", "archaea"}

# Bancos montados na hora a partir de TODOS os grupos indexados em DIRETORIO_BLAST.
BANCOS_DINAMICOS = ["eucariotos", "refseqsoil"]

# Contagem antiga de genomas por grupo, usada só se o manifesto daquele grupo
# ainda não existir (a contagem real vem de taxonomia_local, gerada por
# scripts_auxiliares/gerar_manifesto_taxid.py). Os números fixos que existiam
# antes tinham ficado desatualizados: a soma dos 18 grupos individuais (25.195)
# nem batia com o total do "refseqsoil" (46.190) que deveriam somar.
VALORES_ANTIGOS_FALLBACK = {
    "bacteria": 22550, "archaea": 822, "nematoda": 248, "tardigrada": 6,
    "rotifera": 20, "acari": 145, "collembola": 139, "oligochaeta": 25,
    "formicidae": 213, "isopoda": 14, "myriapoda": 68, "enchytraeidae": 8,
    "isoptera": 50, "platyhelminthes": 103, "amoebozoa": 51, "sar": 599,
    "discoba": 111, "metamonada": 23,
    "coleoptera": 612, "gastropoda": 301, "apoidea": 244, "araneae": 111,
    "scorpiones": 9, "pseudoscorpiones": 1,
}

Banco = namedtuple("Banco", ["nome", "grupos", "caminho_blast", "total_genomas"])


def diretorio_blast():
    return os.environ.get("DIRETORIO_BLAST", DIRETORIO_BLAST_PADRAO)


def grupos_indexados(diretorio=None):
    """Grupos com índice BLAST no diretório (ordem alfabética); [] se o diretório não existir."""
    diretorio = diretorio or diretorio_blast()
    try:
        return sorted({f.split('.')[0] for f in os.listdir(diretorio) if f.endswith('.nsq')})
    except FileNotFoundError:
        return []


def nomes():
    """Todos os nomes de banco aceitos (os do formulário)."""
    return set(BANCOS_COMPOSTOS) | set(APELIDOS) | set(GRUPOS_INDIVIDUAIS) | set(BANCOS_DINAMICOS)


def grupos_do_banco(nome, diretorio=None):
    """Lista de grupos que o banco junta, na ordem do comando do BLAST; None se o banco não existir."""
    if nome in BANCOS_COMPOSTOS:
        return list(BANCOS_COMPOSTOS[nome])
    if nome in APELIDOS:
        return [APELIDOS[nome]]
    if nome in GRUPOS_INDIVIDUAIS:
        return [nome]
    if nome == "eucariotos":
        return [g for g in grupos_indexados(diretorio) if g not in GRUPOS_NAO_EUCARIOTOS]
    if nome == "refseqsoil":
        return grupos_indexados(diretorio)
    return None


def genomas_do_grupo(grupo):
    """Quantos genomas o grupo tem (do manifesto; senão, do valor antigo; senão, 0)."""
    real = taxonomia_local.contagem_organismos_grupo(grupo)
    return real if real is not None else VALORES_ANTIGOS_FALLBACK.get(grupo, 0)


def resolver(nome, diretorio=None):
    """Banco pronto para a busca, ou None se o nome não for um banco conhecido."""
    diretorio = diretorio or diretorio_blast()
    grupos = grupos_do_banco(nome, diretorio)
    if grupos is None:
        return None
    caminho = " ".join(os.path.join(diretorio, g) for g in grupos)
    total = sum(genomas_do_grupo(g) for g in grupos)
    return Banco(nome, grupos, caminho, total)
