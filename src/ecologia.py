"""
Classificação ecológica dos organismos (árvore "Classificação Funcional" do relatório).

Baseada no Global Soil Biodiversity Atlas (2016):
  - "Grande Grupo"     -> Capítulo II (Diversidade dos Organismos do Solo)
  - "Função Ecológica" -> Capítulo IV, p.112 (Ecosystem Functions and Services)

O Cap. IV (p.112) define 4 grupos funcionais para a biota do solo:
  1) Microrganismos                  -> Bactérias, Archaea, Fungos
  2) Micropredadores                 -> Protistas, Nematoides, Tardígrados, Rotíferos
  3) Decompositores da Serrapilheira -> meso/macrofauna que fragmenta a
     serrapilheira: Ácaros, Colêmbolos, Isópodes, Miriápodes, larvas de insetos
  4) Engenheiros do Ecossistema      -> Minhocas, Enquitreídeos, Formigas, Cupins

Grupos que existem no Cap. II mas NÃO se encaixam nos 4 grupos funcionais do
Cap. IV (Moluscos, Plantas/raízes, Vírus, Megafauna/Vertebrados) recebem a
função "Fora do Escopo Principal". Eles continuam aparecendo normalmente na
árvore taxonômica, mas ficam isolados na árvore funcional.

Uso:
    from ecologia import classificar_ecologia
    grande_grupo, tamanho, funcao = classificar_ecologia(["Eukaryota", "Fungi", ...])
"""

# Cada item: (Grande Grupo, Tamanho Biológico, Função Ecológica, [termos])
#
# Os termos são procurados (sem diferenciar maiúsculas) na linhagem do NCBI do
# organismo. A lista é avaliada NA ORDEM: o primeiro grupo cujo termo aparecer
# na linhagem "vence". Por isso grupos mais ESPECÍFICOS (ex: Enchytraeidae) vêm
# ANTES dos mais GENÉRICOS que os englobam (ex: Oligochaeta -> Minhocas), e
# Ácaros vêm antes de Aracnídeos.
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

# Resultado quando nenhuma regra reconhece a linhagem.
NAO_CLASSIFICADO = ("Não Classificado", "Indefinido", "Função Indefinida")

# Todas as funções possíveis (a árvore funcional do relatório começa com uma
# entrada para cada uma, mesmo que fique vazia).
FUNCOES_ECOLOGICAS = sorted({f for _, _, f, _ in REGRAS_CLASSIFICACAO_ECOLOGICA} | {NAO_CLASSIFICADO[2]})


def classificar_ecologia(linhagem):
    """Devolve (grande_grupo, tamanho, funcao_ecologica) para uma linhagem do
    NCBI (lista de nomes, da raiz até a espécie)."""
    tax_str = " ".join(linhagem).lower()
    for grande_grupo, tamanho, funcao_ecologica, termos in REGRAS_CLASSIFICACAO_ECOLOGICA:
        if any(termo in tax_str for termo in termos):
            return grande_grupo, tamanho, funcao_ecologica
    return NAO_CLASSIFICADO
