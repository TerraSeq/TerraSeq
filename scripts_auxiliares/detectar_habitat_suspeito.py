import os
import json
import csv

DIRETORIO_ORIGEM = "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/refseq"
DIRETORIO_MANIFESTOS = "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/manifestos"
CAMINHO_SAIDA = os.path.join(DIRETORIO_MANIFESTOS, "suspeitos_habitat.csv")

# Vasculha os metadados de BioSample (assemblyInfo.biosample.attributes) de
# TODOS os genomas baixados, procurando por palavras-chave que indiquem um
# habitat claramente não-terrestre (marinho, água doce, etc.) nos campos
# ambientais padronizados (MIxS/MIGS: env_broad_scale, env_local_scale,
# env_medium, isolation_source, geo_loc_name...).
#
# IMPORTANTE -- isso NÃO é uma classificação completa de habitat: a maioria
# dos genomas não preenche esses campos (fica "missing"/"not provided"), e
# nesses casos o script simplesmente não vai encontrar nada -- ausência de
# indício aqui NÃO comprova que o organismo é de solo, só significa que essa
# checagem automática não achou sinal nenhum, favorável ou contrário. Serve
# pra reduzir a lista de milhares de organismos pra só os que têm evidência
# concreta no próprio metadado do NCBI, tornando a revisão manual (ou uma
# revisão espécie-por-espécie) viável.

CAMPOS_AMBIENTAIS = {
    "env_broad_scale", "env_local_scale", "env_medium", "isolation_source",
    "habitat", "geo_loc_name", "sample_type", "environment_biome",
    "environment_feature", "environment_material", "host",
}

PALAVRAS_SUSPEITAS = {
    "marine": "marinho",
    "sea water": "água do mar",
    "seawater": "água do mar",
    "ocean": "oceano",
    "estuar": "estuarino",
    "reef": "recife",
    "coral": "coral",
    "coastal": "costeiro",
    "intertidal": "entremarés",
    "pelagic": "pelágico",
    "brackish": "água salobra",
    "freshwater": "água doce",
    "fresh water": "água doce",
    "lake": "lago",
    "river": "rio",
    "aquatic": "aquático",
    "pond": "lagoa",
}

VALORES_VAZIOS = {"missing", "not provided", "n/a", "na", "", "not applicable", "not collected", "unknown"}


def _extrair_sinais_ambientais(dados_genoma):
    sinais = []
    biosample = dados_genoma.get("assemblyInfo", {}).get("biosample", {})

    atributos = biosample.get("attributes", [])
    for attr in atributos:
        nome = (attr.get("name") or "").strip().lower()
        valor = (attr.get("value") or "").strip()
        if nome not in CAMPOS_AMBIENTAIS or valor.lower() in VALORES_VAZIOS:
            continue
        valor_lower = valor.lower()
        for palavra, traducao in PALAVRAS_SUSPEITAS.items():
            if palavra in valor_lower:
                sinais.append(f"{nome}='{valor}' (contém '{palavra}' = {traducao})")

    geo = (biosample.get("geoLocName") or "").strip()
    if geo and geo.lower() not in VALORES_VAZIOS:
        geo_lower = geo.lower()
        for palavra, traducao in PALAVRAS_SUSPEITAS.items():
            if palavra in geo_lower:
                sinais.append(f"geoLocName='{geo}' (contém '{palavra}' = {traducao})")

    return sinais


def varrer_grupo(taxon):
    caminho = os.path.join(DIRETORIO_ORIGEM, taxon, "ncbi_dataset", "data", "assembly_data_report.jsonl")
    resultados = []
    if not os.path.exists(caminho):
        return resultados
    with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            dados = json.loads(linha)
            sinais = _extrair_sinais_ambientais(dados)
            if sinais:
                organismo = dados.get("organism", {}).get("organismName", "Desconhecido")
                acc = dados.get("accession", "")
                resultados.append((taxon, organismo, acc, "; ".join(sinais)))
    return resultados


if __name__ == "__main__":
    print("Vasculhando metadados de BioSample em busca de indícios de habitat não-terrestre...\n")
    os.makedirs(DIRETORIO_MANIFESTOS, exist_ok=True)
    grupos = sorted(f.name for f in os.scandir(DIRETORIO_ORIGEM) if f.is_dir())

    total_suspeitos = 0
    with open(CAMINHO_SAIDA, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["grupo", "organismo", "accession", "indicios_encontrados"])
        for taxon in grupos:
            resultados = varrer_grupo(taxon)
            if resultados:
                print(f"⚠️  {taxon}: {len(resultados)} genoma(s) com indício de habitat suspeito")
            total_suspeitos += len(resultados)
            for linha in resultados:
                writer.writerow(linha)

    print(f"\n✅ Planilha salva em {CAMINHO_SAIDA}")
    print(f"   Total de genomas com indício de habitat suspeito: {total_suspeitos}")
    print("\n⚠️  IMPORTANTE: isso só pega organismos cujo BioSample tem metadado ambiental")
    print("   preenchido com palavra-chave suspeita. A maioria dos genomas não preenche")
    print("   esse metadado (fica \"missing\"/\"not provided\") -- ausência de indício aqui")
    print("   NÃO comprova que é organismo de solo, só que essa checagem não achou nada.")
