import os
import glob
import json
import sqlite3

DIRETORIO_ORIGEM = "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/refseq"
DIRETORIO_MANIFESTOS = "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/manifestos"
CAMINHO_DB = os.path.join(DIRETORIO_MANIFESTOS, "taxid.sqlite")
CAMINHO_CONTAGEM = os.path.join(DIRETORIO_MANIFESTOS, "contagem_organismos.json")

# Gera um manifesto SQLite (accession_sequencia -> taxId) 100% local, sem
# consultar o NCBI pela rede.
#
# Por que SQLite e nao um TSV lido pra um dict Python (como na primeira
# versao deste script): os bancos combinados de solo passam de 90 milhoes
# de sequencias. Um dicionario Python com 90 milhoes de entradas facilmente
# estoura dezenas de GB de RAM sozinho -- o mesmo tipo de problema que
# causou os OOM kills corrigidos em run_parse_blastn.py. Com SQLite, a
# busca usa o indice da PRIMARY KEY (accession) e fica em disco, com uso de
# memoria desprezivel e busca praticamente instantanea mesmo com dezenas de
# milhoes de linhas.
#
# Tambem NAO guardamos o nome do organismo/descricao aqui (so o taxId) --
# isso e redundante: taxonomia_local.linhagem_por_taxid() ja devolve o nome
# do organismo (ultimo elemento da linhagem) a partir do taxId, usando a
# base de taxonomia do NCBI que fica carregada em memoria (essa sim cabe
# tranquilamente, sao so uns 2-3 milhoes de taxons no total, nao centenas
# de milhoes de sequencias).
#
# O NCBI Datasets ja salva, junto de cada genoma baixado, um
# assembly_data_report.jsonl com o taxId do organismo (nivel GENOMA). Cada
# genoma tem varias sequencias/scaffolds dentro dele (nivel SEQUENCIA, que e
# o que aparece como "sseqid" nos hits do BLAST) -- entao cruzamos os dois:
# lemos o taxId de cada genoma (pasta ncbi_dataset/data/<accession_genoma>/)
# e aplicamos esse mesmo taxId a todas as sequencias dentro da pasta dele.

TAMANHO_LOTE = 20_000


def _carregar_taxid_por_genoma(pasta_taxon):
    caminho_relatorio = os.path.join(pasta_taxon, "ncbi_dataset", "data", "assembly_data_report.jsonl")
    mapa = {}
    if not os.path.exists(caminho_relatorio):
        return mapa
    with open(caminho_relatorio, "r", encoding="utf-8", errors="ignore") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            dados = json.loads(linha)
            acc_genoma = dados.get("accession", "")
            taxid = dados.get("organism", {}).get("taxId")
            if acc_genoma and taxid:
                mapa[acc_genoma] = str(taxid)
    return mapa


def gerar_manifesto_taxid(taxon, conexao):
    pasta_taxon = os.path.join(DIRETORIO_ORIGEM, taxon)
    taxid_por_genoma = _carregar_taxid_por_genoma(pasta_taxon)
    if not taxid_por_genoma:
        print(f"  ⚠️ Nenhum assembly_data_report.jsonl encontrado/válido para {taxon}, pulando.")
        return 0

    pasta_dados = os.path.join(pasta_taxon, "ncbi_dataset", "data")
    total_sequencias = 0
    lote = []

    for acc_genoma, taxid in taxid_por_genoma.items():
        pasta_genoma = os.path.join(pasta_dados, acc_genoma)
        arquivos_fna = glob.glob(os.path.join(pasta_genoma, "*.fna"))
        for fna in arquivos_fna:
            with open(fna, "r", errors="ignore") as f:
                for linha in f:
                    if linha.startswith(">"):
                        resto = linha[1:].strip()
                        # Mesma normalizacao que main.py usa antes de
                        # consultar (remove a versao ".1" do accession),
                        # pra bater exatamente com a chave de busca.
                        acc_sequencia = resto.split(" ")[0].split(".")[0]
                        lote.append((acc_sequencia, taxid))
                        total_sequencias += 1
                        if len(lote) >= TAMANHO_LOTE:
                            conexao.executemany("INSERT OR REPLACE INTO sequencias VALUES (?, ?)", lote)
                            lote = []

    if lote:
        conexao.executemany("INSERT OR REPLACE INTO sequencias VALUES (?, ?)", lote)
    conexao.commit()

    print(f"  -> {taxon}: {total_sequencias} sequência(s) mapeada(s) de {len(taxid_por_genoma)} genoma(s)")
    return len(taxid_por_genoma)


if __name__ == "__main__":
    print("Gerando manifesto de taxId (accession -> taxId), 100% local, em SQLite.\n")
    os.makedirs(DIRETORIO_MANIFESTOS, exist_ok=True)

    # Manifestos antigos em TSV (de uma versão anterior deste script) não são
    # mais usados -- o manifesto agora é só o banco SQLite abaixo.
    for tsv_antigo in glob.glob(os.path.join(DIRETORIO_MANIFESTOS, "*_taxid.tsv")):
        os.remove(tsv_antigo)

    conexao = sqlite3.connect(CAMINHO_DB)
    # synchronous=OFF e journal_mode=MEMORY aceleram MUITO a carga em lote
    # (evita fsync a cada commit). Seguro aqui porque esse banco é 100%
    # derivado/regenerável -- se corromper por uma queda de energia no meio
    # da geração, basta rodar o script de novo.
    conexao.execute("PRAGMA synchronous = OFF")
    conexao.execute("PRAGMA journal_mode = MEMORY")
    conexao.execute("CREATE TABLE IF NOT EXISTS sequencias (accession TEXT PRIMARY KEY, taxid TEXT NOT NULL)")

    grupos = [f.name for f in os.scandir(DIRETORIO_ORIGEM) if f.is_dir()]
    contagem_por_grupo = {}
    for taxon in grupos:
        print(f"🧬 {taxon}")
        contagem_por_grupo[taxon] = gerar_manifesto_taxid(taxon, conexao)

    conexao.close()

    # Contagem REAL de genomas (organismos) por grupo, a partir dos
    # assembly_data_report.jsonl -- usada em main.py/main_issues.py pra
    # calcular "Genomas no Banco (Grupo)" e a Cobertura Estimada. Antes esses
    # totais eram digitados manualmente no código (BANCOS_DISPONIVEIS) e
    # ficaram desatualizados (a soma dos 18 grupos não batia nem com o total
    # combinado "refseqsoil" que eles mesmos deveriam somar).
    with open(CAMINHO_CONTAGEM, "w", encoding="utf-8") as f:
        json.dump(contagem_por_grupo, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Manifesto gerado em {CAMINHO_DB}.")
    print(f"✅ Contagem de genomas por grupo salva em {CAMINHO_CONTAGEM}.")
    print("   A etapa de classificação taxonômica no main.py agora roda 100% local (sem consultar o NCBI pela")
    print("   rede), exceto pra sequências que não estejam mapeadas aqui.")
