"""
Leitura do resultado do BLAST: o CSV de pares de primers válidos que
primer_blast_local.py grava (<prefixo>__results.pass.csv), uma linha por
amplicon.

    import resultados_blast
    hits = resultados_blast.ler_hits(caminho_do_csv)
    hits.por_sequencia     # {subject_id: [amplicon, ...]}, na ordem do CSV
    hits.total             # número de amplicons (linhas do CSV)
    hits.media_amplicon    # tamanho médio dos amplicons, em bp

    sequencias = resultados_blast.separar_sequencias_completas(metadados_por_especie)
"""
import csv
import os
from collections import namedtuple

from arvore_taxonomica import accession_do_id

# Limite global (não por espécie) de caracteres de sequência de amplicon
# guardados DIRETO no result.json. Sem isso, buscas com muitos hits geram um
# JSON gigante -- já passou dos 145MB, estourando o limite de 100MB por arquivo
# do GitHub e travando o push do relatório. O corte é só na sequência: o resto
# do amplicon (acc/size/tm/start/end) é salvo para TODOS, então nenhuma
# estatística é perdida.
ORCAMENTO_MAX_CARACTERES_SEQ = 15_000_000
# As sequências que ficam de fora do result.json NÃO são descartadas: vão para
# sequencias_completas.json, que o botão "Baixar FASTA" do relatório busca só
# quando clicado. Esse arquivo tem orçamento próprio, bem maior (ainda dentro
# do limite de 100MB do GitHub). Só se estourar os DOIS a sequência fica
# disponível apenas no servidor de processamento.
ORCAMENTO_MAX_CARACTERES_SEQ_COMPLETA = 80_000_000

AVISO_SEQ_NO_FASTA = "Sequência não exibida neste relatório (limite de tamanho do arquivo) — clique em \"Baixar FASTA\" para obtê-la."
AVISO_SEQ_SO_NO_SERVIDOR = "Sequência não incluída neste relatório (limite de tamanho do arquivo atingido) — dados brutos preservados no servidor de processamento."

Hits = namedtuple("Hits", ["por_sequencia", "total", "media_amplicon"])


def extrair_campo_flexivel(dicionario_linha, palavra_chave, padrao="N/A"):
    """Valor da primeira coluna cujo nome contém a palavra-chave (sem diferenciar maiúsculas)."""
    for coluna, valor in dicionario_linha.items():
        if coluna and palavra_chave.lower() in coluna.lower():
            return valor
    return padrao


def ler_hits(arquivo_pass):
    """Lê o CSV de pares válidos. Arquivo inexistente = nenhum hit."""
    # dict: guarda a ordem do CSV (a ordem das sequências decide a ordem das
    # árvores e qual accession aparece no card de espécies com várias sequências).
    por_sequencia = {}
    total = 0
    soma_amplicon = 0
    caracteres_seq = 0
    caracteres_completa = 0

    if os.path.exists(arquivo_pass):
        with open(arquivo_pass, mode='r', encoding='utf-8') as f:
            for linha in csv.DictReader(f):
                total += 1
                sid = linha.get('Subject_ID', 'Desconhecido')

                try:
                    soma_amplicon += int(extrair_campo_flexivel(linha, "size", "0"))
                except (TypeError, ValueError):
                    pass

                tm_real = "N/A"
                for chave, valor in linha.items():
                    if chave and "amplicon_tm" in chave.lower().strip():
                        tm_real = valor
                        break

                # Sequência do amplicon, dentro dos orçamentos de tamanho (ver acima).
                seq_original = linha.get('Amplicon_sequence', linha.get('amplicon_sequence', 'Sequência indisponível'))
                seq_omitida = False
                seq_completa_disponivel = False
                seq_amplicon = seq_original
                if caracteres_seq < ORCAMENTO_MAX_CARACTERES_SEQ:
                    caracteres_seq += len(seq_original)
                else:
                    seq_omitida = True
                    if caracteres_completa < ORCAMENTO_MAX_CARACTERES_SEQ_COMPLETA:
                        caracteres_completa += len(seq_original)
                        seq_completa_disponivel = True
                        seq_amplicon = AVISO_SEQ_NO_FASTA
                    else:
                        seq_amplicon = AVISO_SEQ_SO_NO_SERVIDOR

                por_sequencia.setdefault(sid, []).append({
                    "acc": accession_do_id(sid),
                    "size": extrair_campo_flexivel(linha, "size", "N/A"),
                    "tm": tm_real,
                    "start": extrair_campo_flexivel(linha, "start", "N/A"),
                    "end": extrair_campo_flexivel(linha, "end", "N/A"),
                    "seq": seq_amplicon,
                    # Diz ao template.html se pode oferecer o download (senão ele
                    # baixaria o texto de aviso como se fosse a sequência).
                    "omitido": seq_omitida,
                    # Só em memória: separar_sequencias_completas() tira daqui e
                    # leva para sequencias_completas.json antes de gravar o result.json.
                    "_seq_completa": seq_original if seq_completa_disponivel else None,
                    # Hits BRUTOS do BLAST (fwd+rev, antes de validar Tm/mismatch) do
                    # genoma inteiro -- calculado em _evaluate_hit_loc (run_parse_blastn.py),
                    # que para no 1º par válido por genoma.
                    "raw_hits_genoma": extrair_campo_flexivel(linha, "Raw_hits_no_genoma", "N/A"),
                })

    media = (soma_amplicon / total) if total > 0 else 0
    return Hits(por_sequencia, total, media)


def separar_sequencias_completas(metadados_por_especie):
    """Tira o campo temporário "_seq_completa" de cada amplicon e devolve
    {especie: [sequência ou None, ...]} só das espécies que têm alguma."""
    sequencias = {}
    for especie, dados in metadados_por_especie.items():
        lista = [amp.pop("_seq_completa", None) for amp in dados["amplicons"]]
        if any(s is not None for s in lista):
            sequencias[especie] = lista
    return sequencias
