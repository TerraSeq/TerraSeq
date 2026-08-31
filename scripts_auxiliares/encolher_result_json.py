import sys
import json
import os

# Aplica retroativamente o mesmo orcamento de tamanho que main.py/main_issues.py
# agora aplicam na geracao: limita o total de caracteres de sequencia de
# amplicon guardados no result.json, pra caber no limite de 100MB por arquivo
# do GitHub. Usa isso em relatorios ja gerados ANTES dessa correcao (ex:
# result.json travado num commit local porque passou de 100MB).
#
# Uso: python3 scripts_auxiliares/encolher_result_json.py <caminho_result.json>

ORCAMENTO_MAX_CARACTERES_SEQ = 15_000_000
MENSAGEM_OMITIDA = "Sequência não incluída neste relatório (limite de tamanho do arquivo atingido) — dados brutos preservados no servidor de processamento."


def encolher(caminho):
    tamanho_antes = os.path.getsize(caminho)
    with open(caminho, "r", encoding="utf-8") as f:
        dados = json.load(f)

    caracteres_acumulados = 0
    total_sequencias = 0
    total_omitidas = 0

    for especie_info in dados.get("leaf_metadata", {}).values():
        for amplicon in especie_info.get("amplicons", []):
            seq = amplicon.get("seq", "")
            total_sequencias += 1
            if caracteres_acumulados < ORCAMENTO_MAX_CARACTERES_SEQ:
                caracteres_acumulados += len(seq)
            elif not amplicon.get("omitido"):
                amplicon["seq"] = MENSAGEM_OMITIDA
                amplicon["omitido"] = True
                total_omitidas += 1

    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, separators=(",", ":"))

    tamanho_depois = os.path.getsize(caminho)
    print(f"Sequências no relatório: {total_sequencias} | omitidas agora: {total_omitidas}")
    print(f"Tamanho: {tamanho_antes/1024/1024:.1f}MB -> {tamanho_depois/1024/1024:.1f}MB")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python3 scripts_auxiliares/encolher_result_json.py <caminho_result.json>")
        sys.exit(1)
    encolher(sys.argv[1])
