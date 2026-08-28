import os
import glob
import json
import subprocess

DIRETORIO_ORIGEM = "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/refseq"
DIRETORIO_BLAST = "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/blast_dbs"
DIRETORIO_MANIFESTOS = "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/manifestos"

# Sequências identificadas na auditoria de agosto/2026 (tamanho de sequência
# anormal nos bancos combinados) como organismos fora do escopo de solo.
# O preparar_blast.py descarta o nome do organismo ao indexar (fica só o ID),
# por isso este script gera um manifesto accession -> organismo ANTES de
# tocar em qualquer arquivo, preservando essa informação para auditorias futuras.
#
# HISTÓRICO: essas 4 exclusões originais foram feitas por ACCESSION (não por
# taxId) porque, na época, só tínhamos os 1-3 maiores outliers de cada
# espécie (identificados via "maior sequência do banco"), não a lista
# completa de sequências. Descobrimos depois (blastdbcmd -entry all no
# isopoda, pós-curadoria) que a Anilocra frontalis tinha MAIS cromossomos
# grandes além dos 3 capturados manualmente (OZ209258.1-OZ209262.1 e
# possivelmente outros seguiam sem ser removidos) -- por isso foram
# migradas pra TAXIDS_EXCLUIDOS abaixo, que resolve automaticamente
# TODAS as sequências do genoma, não só as que a auditoria manual pegou.
ACCESSIONS_EXCLUIDAS = {}

# Segunda rodada de curadoria (levantamento completo de organismos por
# grupo + revisão manual, setembro/2026): organismos com CHANCE ZERO de
# ocorrer em solo (marinhos obrigatórios -- algas marrons, parasitas de
# hospedeiro exclusivamente marinho, meiofauna intersticial marinha, etc.),
# identificados pelo taxId (nível de organismo/genoma) em vez de accession
# de sequência -- são resolvidos automaticamente pra todas as sequências
# daquele genoma em _resolver_taxids_para_accessions().
TAXIDS_EXCLUIDOS = {
    "ascomycota": {
        "161743": "Ramulispora sorghi f. maydis (taxId mal-atribuido -- biosample da NCBI descreve como 'Uncultivated OLB16 bacterium', MAG remontado de metagenoma de agua do mar do Oceano Artico/Canada Basin, nao e nem fungo cultivado)",
    },
    "amoebozoa": {
        "1077153": "Paramoeba atlantica (ameba marinha, associada a ouriço-do-mar)",
        "1321612": "Paramoeba invadens (ameba marinha, associada a ouriço-do-mar)",
        "180228": "Paramoeba pemaquidensis (ameba marinha)",
        "1621016": "Entamoeba marina (ameba marinha)",
    },
    "discoba": {
        "140242": "Cruzella marina (cinetoplastídeo marinho)",
        "91374": "Diplonema papillatum (diplonemídeo planctônico marinho)",
        "2508216": "Diplonema japonicum (diplonemídeo planctônico marinho)",
        "630703": "Rhynchopus euleeides (diplonemídeo planctônico marinho)",
        "2016123": "Rhynchopus humris (diplonemídeo planctônico marinho)",
        "38248": "Trypanosoma boissoni (parasita de sangue de tubarão/raia)",
    },
    "isopoda": {
        "2925007": "Anilocra frontalis (isópode parasita marinho de peixes)",
        "1955234": "Bathynomus jamesi (isópode gigante de fossa abissal)",
        "2922061": "Ceratothoa steindachneri (parasita de brânquia de peixe marinho)",
        "2067965": "Jaera ischiosetosa (isópode de costão rochoso marinho)",
        "2613951": "Jaera praehirsuta (isópode de costão rochoso marinho)",
        "96851": "Jaera albifrons (isópode de costão rochoso marinho)",
    },
    "nematoda": {
        "6257": "Parascaris univalens (nematódeo parasita de equinos)",
        "320140": "Sabatieria punctata (nematódeo de sedimento marinho)",
        "3040841": "Trissonchulus latispiculum (nematódeo de sedimento marinho)",
        "2505740": "Enoplolaimus lenunculus (nematódeo de sedimento marinho)",
        "3040840": "Trileptium ribeirensis (nematódeo de sedimento marinho)",
        "320139": "Daptonema setosum (nematódeo de sedimento marinho)",
        "1654675": "Litoditis marina (nematódeo marinho)",
        "319955": "Sphaerolaimus hirsutus (nematódeo de sedimento marinho)",
        "303229": "Anisakis pegreffii (parasita de peixe/mamífero marinho)",
        "6269": "Anisakis simplex (parasita de peixe/mamífero marinho)",
        "6271": "Pseudoterranova decipiens (parasita de peixe/mamífero marinho)",
        "944443": "Echinomermella matsi (parasita de ouriço-do-mar)",
    },
    "platyhelminthes": {
        "983666": "Pseudobiceros splendidus (platelminto marinho)",
        "163373": "Schmidtea nova (planária de água doce, não terrestre)",
        "2991682": "Nematoplana nigrocapitula (turbelário intersticial marinho)",
        "2991685": "Vannuccia rotundouncinata (turbelário intersticial marinho)",
        "2991684": "Coelogynopora nodosa (turbelário intersticial marinho)",
        "2991686": "Parotoplana pacifica (turbelário intersticial marinho)",
        "2991687": "Invenusta paracnida (turbelário intersticial marinho)",
        "2991690": "Americanaplana fernaldi (turbelário intersticial marinho)",
        "2991683": "Monocelis spectator (turbelário intersticial marinho)",
        "2991688": "Minona dolichovesicula (turbelário intersticial marinho)",
        "2291463": "Prostheceraeus crozeri (polyclad marinho)",
        "2730667": "Benedenia humboldti (parasita de peixe marinho)",
        "335511": "Cardicola forsteri (parasita de sangue de atum de cultivo marinho)",
        "282301": "Macrostomum lignano (organismo-modelo marinho/salobro)",
    },
    "rotifera": {
        "104778": "Seison nebaliae (epizoico de crustáceo marinho)",
    },
    "sar": {
        "117523": "Nereocystis luetkeana (alga marrom/kelp marinha)",
        "169782": "Pterygophora californica (alga marrom/kelp marinha)",
        "105409": "Egregia menziesii (alga marrom/kelp marinha)",
        "309354": "Cymathaere triplicata (alga marrom/kelp marinha)",
        "169770": "Laminaria sinclairii (alga marrom/kelp marinha)",
        "2872": "Costaria costata (alga marrom/kelp marinha)",
        "309364": "Laminaria ephemera (alga marrom/kelp marinha)",
        "572309": "Neoagarum fimbriatum (alga marrom/kelp marinha)",
        "98221": "Alaria marginata (alga marrom/kelp marinha)",
        "105414": "Postelsia palmaeformis (alga marrom/kelp marinha)",
        "169769": "Laminaria setchellii (alga marrom/kelp marinha)",
        "98222": "Alaria nana (alga marrom/kelp marinha)",
        "2724434": "Hedophyllum nigripes (alga marrom/kelp marinha)",
        "243268": "Phaeostrophion irregulare (alga marrom/kelp marinha)",
        "381692": "Padina boergesenii (alga marrom marinha)",
        "531973": "Dictyopteris delicatula (alga marrom marinha)",
        "2880": "Ectocarpus siliculosus (alga marrom marinha)",
        "690460": "Ectocarpus crouaniorum (alga marrom marinha)",
        "116065": "Choristocarpus tenellus (alga marrom marinha)",
        "376270": "Discosporangium mesarthrocarpum (alga marrom marinha)",
        "3012": "Fucus distichus (alga marrom marinha)",
        "43935": "Ectocarpus fasciculatus (alga marrom marinha)",
        "2885": "Pylaiella littoralis (alga marrom marinha)",
        "74478": "Himanthalia elongata (alga marrom marinha)",
        "52969": "Ascophyllum nodosum (alga marrom marinha)",
        "74467": "Pelvetia canaliculata (alga marrom marinha)",
        "588760": "Halopteris paniculata (alga marrom marinha)",
        "99931": "Desmarestia dudresnayi (alga marrom marinha)",
        "64930": "Myriotrichia clavaeformis (alga marrom marinha)",
        "1964287": "Feldmannia mitchelliae (alga marrom marinha)",
        "2876": "Dictyota dichotoma (alga marrom marinha)",
        "2567908": "Hapterophycus canaliculatus (alga marrom/kelp marinha)",
        "87148": "Fucus serratus (alga marrom marinha)",
        "1205903": "Desmarestia herbacea (alga marrom marinha)",
        "80365": "Laminaria digitata (alga marrom/kelp marinha)",
        "64904": "Chordaria linearis (alga marrom marinha)",
        "590117": "Ericaria zosteroides (alga marrom marinha)",
        "74381": "Undaria pinnatifida (alga marrom/kelp marinha)",
        "416828": "Saccharina sessilis (alga marrom/kelp marinha)",
        "143165": "Sargassum natans (alga marrom marinha)",
        "115959": "Sargassum obtusifolium (alga marrom marinha)",
        "143163": "Sargassum fluitans (alga marrom marinha)",
        "143166": "Sargassum platycarpum (alga marrom marinha)",
        "27967": "Scytosiphon lomentaria (alga marrom marinha)",
        "88149": "Saccharina japonica (alga marrom/kelp marinha)",
        "416830": "Saccharina sculpera (alga marrom/kelp marinha)",
        "2841634": "Sphaerotrichia firma (alga marrom marinha)",
        "117516": "Sphacelaria rigidula (alga marrom marinha)",
        "309358": "Saccharina latissima (alga marrom/kelp marinha)",
        "66620": "Saccorhiza dermatodea (alga marrom/kelp marinha)",
        "1403536": "Scytosiphon promiscuus (alga marrom marinha)",
        "45365": "Saccorhiza polyschides (alga marrom/kelp marinha)",
        "1442163": "Sargassum wightii (alga marrom marinha)",
    },
}

GRUPOS_AFETADOS = sorted(set(ACCESSIONS_EXCLUIDAS.keys()) | set(TAXIDS_EXCLUIDOS.keys()))


def _resolver_taxids_para_accessions(taxon):
    """Resolve os taxIds banidos de um grupo (nível organismo/genoma) pras
    accessions de sequência específicas dentro de cada genoma, lendo o
    assembly_data_report.jsonl (taxId de cada genoma) e os cabeçalhos dos
    .fna daquele genoma (accession de cada sequência dentro dele)."""
    taxids_banidos = TAXIDS_EXCLUIDOS.get(taxon)
    if not taxids_banidos:
        return {}

    pasta_taxon = os.path.join(DIRETORIO_ORIGEM, taxon)
    caminho_relatorio = os.path.join(pasta_taxon, "ncbi_dataset", "data", "assembly_data_report.jsonl")
    genomas_banidos = {}  # accession_genoma -> motivo
    if os.path.exists(caminho_relatorio):
        with open(caminho_relatorio, "r", encoding="utf-8", errors="ignore") as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                dados = json.loads(linha)
                taxid = str(dados.get("organism", {}).get("taxId", ""))
                if taxid in taxids_banidos:
                    genomas_banidos[dados.get("accession", "")] = taxids_banidos[taxid]

    accessions_resolvidas = {}
    pasta_dados = os.path.join(pasta_taxon, "ncbi_dataset", "data")
    for acc_genoma, motivo in genomas_banidos.items():
        pasta_genoma = os.path.join(pasta_dados, acc_genoma)
        for fna in glob.glob(os.path.join(pasta_genoma, "*.fna")):
            with open(fna, "r", errors="ignore") as f:
                for linha in f:
                    if linha.startswith(">"):
                        acc_seq = linha[1:].split(" ")[0].strip()
                        accessions_resolvidas[acc_seq] = motivo
    return accessions_resolvidas


def gerar_manifesto(taxon):
    pasta_alvo = os.path.join(DIRETORIO_ORIGEM, taxon)
    arquivos_fna = glob.glob(os.path.join(pasta_alvo, "**", "*.fna"), recursive=True)
    os.makedirs(DIRETORIO_MANIFESTOS, exist_ok=True)
    caminho_manifesto = os.path.join(DIRETORIO_MANIFESTOS, f"{taxon}.tsv")
    with open(caminho_manifesto, "w") as out:
        for fna in arquivos_fna:
            with open(fna, "r", errors="ignore") as f:
                for line in f:
                    if line.startswith(">"):
                        accession = line[1:].split(" ")[0].strip()
                        descricao = line[1:].strip()
                        out.write(f"{accession}\t{descricao}\n")
    print(f"  -> Manifesto salvo em {caminho_manifesto}")


def filtrar_e_reindexar(taxon, banidos):
    pasta_alvo = os.path.join(DIRETORIO_ORIGEM, taxon)
    arquivos_fna = glob.glob(os.path.join(pasta_alvo, "**", "*.fna"), recursive=True)
    base_out = os.path.join(DIRETORIO_BLAST, taxon)
    temp_fasta = os.path.join(pasta_alvo, "banco_curado.fasta")

    print(f"  -> Filtrando {len(banidos)} sequência(s) banida(s) de {len(arquivos_fna)} arquivo(s)...")
    removidos = 0
    with open(temp_fasta, "w") as outfile:
        for fna in arquivos_fna:
            manter = True
            with open(fna, "r", errors="ignore") as infile:
                for line in infile:
                    if line.startswith(">"):
                        accession = line[1:].split(" ")[0].strip()
                        manter = accession not in banidos
                        if not manter:
                            removidos += 1
                            continue
                        line = f"{line.split(' ')[0]}\n"
                    if manter:
                        outfile.write(line)

    print(f"  -> {removidos} sequência(s) removida(s).")

    for f in glob.glob(f"{base_out}*"):
        os.remove(f)

    comando = [
        "makeblastdb", "-in", temp_fasta, "-dbtype", "nucl",
        "-out", base_out, "-title", f"Banco {taxon.capitalize()} (curado)",
        "-parse_seqids",
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    os.remove(temp_fasta)
    if resultado.returncode == 0:
        print(f"✅ {taxon} reindexado com sucesso, sem os organismos fora de escopo.")
    else:
        print(f"❌ Erro ao reindexar {taxon}: {resultado.stderr}")


if __name__ == "__main__":
    print("PASSO 1/2: gerando manifestos (accession -> organismo) de todos os grupos baixados.")
    print("Isso preserva a identificação das espécies mesmo que os .fna sejam apagados depois,")
    print("já que o preparar_blast.py descarta essa informação ao indexar.\n")
    todos_grupos = [f.name for f in os.scandir(DIRETORIO_ORIGEM) if f.is_dir()]
    for taxon in todos_grupos:
        print(f"🧬 {taxon}")
        gerar_manifesto(taxon)

    print("\nPASSO 2/2: removendo organismos fora do escopo (solo) e reindexando os bancos afetados.\n")
    for taxon in GRUPOS_AFETADOS:
        print("-" * 50)
        print(f"🧹 Curando {taxon.upper()}...")

        banidos = dict(ACCESSIONS_EXCLUIDAS.get(taxon, {}))
        for acc, motivo in banidos.items():
            print(f"   - removendo {acc}: {motivo}")

        if taxon in TAXIDS_EXCLUIDOS:
            resolvidos = _resolver_taxids_para_accessions(taxon)
            especies_unicas = sorted(set(resolvidos.values()))
            for especie in especies_unicas:
                print(f"   - removendo (via taxId): {especie}")
            banidos.update(resolvidos)

        filtrar_e_reindexar(taxon, banidos)

    print("\n" + "=" * 60)
    print("🎉 CURADORIA CONCLUÍDA.")
    print("Bancos afetados: " + ", ".join(GRUPOS_AFETADOS))
    print("Rode 'blastdbcmd -db data/blast_dbs/<grupo> -info' para conferir a nova contagem.")
    print("=" * 60)
