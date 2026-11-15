"""
A análise de um pedido, do começo ao fim (run_pipeline), usada pelos dois
monitores: main.py (Google Forms/planilha) e main_issues.py (GitHub Issues).
Cada um só lê o pedido do seu jeito e chama run_pipeline(req, req_id, origem).

Etapas de run_pipeline (cada uma num módulo):
  1. valida o pedido e lê os parâmetros         (notificacoes.py, ler_parametros)
  2. escolhe o banco                             (bancos.py)
  3. roda o BLAST                                (primer_blast_local.py -> run_parse_blastn.py)
  4. lê os amplicons encontrados                 (resultados_blast.py)
  5. monta as árvores                            (arvore_taxonomica.py, ecologia.py)
  6. calcula cobertura e grava o relatório       (relatorio.py)

Quem publica (vitrine, git, e-mail) é o monitor, depois que run_pipeline termina
(publicacao.py).
"""
import os
import subprocess
import sys
import time

import bancos
import bloqueios
import notificacoes
import relatorio
import resultados_blast
import taxonomia_local
from arvore_taxonomica import construir_arvore_aninhada

RAIZ_PROJETO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Teto de hits do BLAST (--max_target_seqs). O pesquisador não escolhe mais (o
# campo saiu do formulário): é sempre este valor.
#
# Histórico: em 03/09/2026 um pedido com 30000 + --amp_seq consumiu ~123GB de
# RAM (máquina de 125GB) e foi morto pelo OOM killer -- mas o culpado era o
# PYTHON (pareamento fwd x rev O(N²) e extração do amplicon de TODO hit bruto),
# já corrigido em run_parse_blastn.py (agrupa por genoma e para no 1º par
# válido). Em 17/09/2026 descobrimos que um teto baixo (5000) tem um efeito
# colateral sério: é um teto do PRÓPRIO blastn por CONTIG, aplicado durante a
# busca -- com bancos combinados grandes (~8.400 genomas), poucos genomas
# fragmentados consomem a cota e o blastn nem chega nos outros, sem erro, só
# cobertura artificialmente baixa (8.466 genomas no banco, só 227 cobertos com
# 5000). Testado com 30000: pico de ~114GB só no blastn, sem OOM; como o
# blastn termina ANTES da extração de amplicons (a memória não acumula),
# 30000 é o teto.
LIMITE_MAXIMO_HITS = 30000


def ler_parametros(req):
    """Parâmetros da busca, como texto para a linha de comando do BLAST
    (campo vazio no pedido = valor padrão)."""
    return {
        "min_size": str(req.get('Tamanho do amplicon: MIN', 20) or 20),
        "max_size": str(req.get('Tamanho do amplicon: MAX', 9999) or 9999),
        "mismatches": int(req.get('Máximo de Mismatches na extremidade 3', 0) or 0),
        "e_value": str(req.get('E-value máximo', 10.0) or 10.0),
        "cobertura": str(req.get('Cobertura mínima', 0) or 0),
        "max_hits": str(LIMITE_MAXIMO_HITS),
        "tm_min": str(req.get('Temperatura de Melting mínima (Tm)', 0) or 0),
    }


def ler_primers(req, req_id):
    """Primers em maiúsculas e o nome do par (se não veio, usa a região alvo ou o ID)."""
    alvo = str(req.get('Região alvo', '')).strip()
    nome_par = str(req.get('Nome do Par de Primers', '')).strip()
    if not nome_par:
        nome_par = f"Par {alvo}" if alvo else f"Par {req_id}"
    return {
        "forward": str(req.get('Primer forward', '')).strip().upper(),
        "reverse": str(req.get('Primer reverse', '')).strip().upper(),
        "pair_name": nome_par,
    }


def escolher_banco(req):
    """O banco pedido; se não existir, devolve o pedido ao pesquisador (PedidoInvalido)
    em vez de cair em silêncio num banco qualquer."""
    nome = str(req.get('Banco de Dados', 'refseqsoil')).strip().lower()
    banco = bancos.resolver(nome)
    if banco is None:
        raise notificacoes.PedidoInvalido(
            notificacoes.validar_pedido(req, bancos_validos=bancos.nomes())
            or [(f'Banco de dados "{nome}" não reconhecido.', f'Database "{nome}" not recognized.')]
        )
    return banco


def montar_comando_blast(banco, caminho_primer, prefixo_saida, parametros):
    return [
        sys.executable, "primer_blast_local.py",
        "-g", banco.caminho_blast, "-p", caminho_primer, "-o", prefixo_saida,
        "-e", parametros["e_value"], "--min_size", parametros["min_size"], "--max_size", parametros["max_size"],
        "-m", parametros["tm_min"], "--max_3prime_mismatches", str(parametros["mismatches"]),
        "--qcov_hsp_perc", parametros["cobertura"], "--max_target_seqs", parametros["max_hits"],
        # -num_threads=1 é proposital: com >1 thread e um banco combinado com
        # bancos "split" em múltiplos volumes (bacteria, ascomycota, sar,
        # platyhelminthes...), o blastn trava com um NULL pointer dentro de
        # BlastFormatter_PreFetchSequenceData/x_RunMTBySplitDB ao buscar as
        # sequências do amplicon (qseq/sseq no outfmt) -- bug conhecido do
        # próprio NCBI BLAST+ (multithread + split DB + outfmt com sequência).
        # Com 1 thread fica mais lento, mas não trava.
        "-t", "1",
        "--amp_seq",
    ]


def rodar_blast(cmd_blast, banco):
    """Roda o BLAST e devolve quantos segundos levou. Banco grande = uma busca por
    vez em todo o servidor (formulário e Issues juntos); a espera fica FORA do cronômetro."""
    pesado = banco.total_genomas >= bloqueios.LIMITE_BANCO_PESADO
    with bloqueios.bloqueio_se(pesado, "blast-pesado", "⏳ Outra análise com banco grande está rodando; aguardando a vez para não estourar a memória do servidor..."):
        inicio = time.time()
        subprocess.run(cmd_blast, cwd=RAIZ_PROJETO, check=True, capture_output=True, text=True)
        return time.time() - inicio


def run_pipeline(req, req_id, origem="PEDIDO"):
    """Roda a análise completa de um pedido: valida, roda o BLAST, monta as
    árvores e grava o relatório em docs/reports/<req_id>/.

    req: o pedido já em português (chaves "Primer forward", "Banco de Dados"...).
    origem: só para o log ("PLANILHA" no main.py, "ISSUE" no main_issues.py).

    Devolve (caminho_relativo_do_relatorio, resultado_json).
    """
    # 1. Pedido: o que o pesquisador pode corrigir (primer inválido, número fora
    #    do formato...) volta pra ele com a lista, antes de qualquer BLAST.
    problemas = notificacoes.validar_pedido(req)
    if problemas:
        raise notificacoes.PedidoInvalido(problemas)

    pasta_resultado = os.path.join(RAIZ_PROJETO, f"docs/reports/{req_id}")
    os.makedirs(pasta_resultado, exist_ok=True)

    primers = ler_primers(req, req_id)
    caminho_primer = os.path.join(pasta_resultado, "primer.fasta")
    with open(caminho_primer, "w") as f:
        f.write(f">Ensaio_{req_id}|Target|fwd\n{primers['forward']}\n")
        f.write(f">Ensaio_{req_id}|Target|rev\n{primers['reverse']}\n")
    parametros = ler_parametros(req)

    # 2. Banco
    banco = escolher_banco(req)

    # 3. BLAST
    prefixo_saida = os.path.join(pasta_resultado, "saida")
    cmd_blast = montar_comando_blast(banco, caminho_primer, prefixo_saida, parametros)
    print(f"\n🔍 Rodando BLAST ({req_id}) no banco {banco.nome}...")
    print("🤖 Comando exato que o Script montou:")
    print(" ".join(cmd_blast))
    print("-" * 50)
    print(f"\n🕵️‍♂️ RAIO-X DA {origem} (O que o Python realmente está lendo):")
    for chave, valor in req.items():
        print(f"Coluna: '{chave}' | Valor recebido: '{valor}'")
    print("⚙️ Rodando programa...")
    segundos = rodar_blast(cmd_blast, banco)
    print(f"⏱️ Tempo de execução do banco '{banco.nome}': {int(segundos // 60)}m {int(segundos % 60)}s")

    # 4. Amplicons encontrados
    hits = resultados_blast.ler_hits(f"{prefixo_saida}__results.pass.csv")
    ids_com_hit = list(hits.por_sequencia)

    # 5. Árvores
    print("⚙️ Preparando montagem taxonômica...")
    arvore, metadados, papeis_funcionais = construir_arvore_aninhada(ids_com_hit, hits.total, hits.por_sequencia)
    for dados_especie in metadados.values():
        dados_especie["genomas_capturados"] = taxonomia_local.contar_genomas_distintos(
            [amp["acc"] for amp in dados_especie["amplicons"]]
        )

    # 6. Cobertura, avisos e relatório
    nao_capturados, aviso_nao_capturados = relatorio.calcular_organismos_nao_capturados(
        RAIZ_PROJETO, banco.grupos, metadados.keys()
    )
    sequencias_completas = resultados_blast.separar_sequencias_completas(metadados)
    genomas_capturados = taxonomia_local.contar_genomas_distintos(ids_com_hit)
    cobertura = relatorio.calcular_cobertura(genomas_capturados, banco.total_genomas)
    avisos = relatorio.avisos_do_relatorio(cobertura, parametros["mismatches"], aviso_nao_capturados)

    resultado_json = relatorio.montar_resultado(
        req, req_id, parametros, banco, primers, hits, genomas_capturados,
        arvore, metadados, papeis_funcionais, nao_capturados, avisos, cobertura,
    )
    relatorio.gravar(pasta_resultado, resultado_json, sequencias_completas, RAIZ_PROJETO)
    return f"docs/reports/{req_id}", resultado_json
