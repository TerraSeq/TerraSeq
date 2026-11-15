"""
O relatório de uma análise: o result.json que docs/template.html lê, e os
arquivos que vão junto em docs/reports/<req_id>/.

    import relatorio
    resultado = relatorio.montar_resultado(...)
    relatorio.gravar(pasta, resultado, sequencias_completas, raiz_projeto)
"""
import json
import os
import shutil
from datetime import datetime

# Parâmetros fixos do BLAST (run_parse_blastn.py), registrados no relatório.
BLAST_TASK = "blastn-short"
WORD_SIZE = 7
DBSIZE = 1_000_000_000          # DBSIZE_REFERENCIA de run_parse_blastn.py

COBERTURA_BAIXA = 0.60          # abaixo disso o relatório avisa


def calcular_organismos_nao_capturados(raiz_projeto, grupos_do_banco, especies_capturadas):
    """
    Retorna a lista de organismos catalogados nos grupos pesquisados que o
    primer NÃO capturou nesta análise (por nome de espécie, mesmo nível do
    "leaf_metadata"/árvore taxonômica -- não é a mesma unidade "por genoma"
    da Cobertura Estimada, ver calcular_cobertura).

    Pedido explícito de um orientador usando a plataforma: o relatório só
    mostrava quem FOI capturado; para decidir se um primer serve pra um
    estudo, também precisa saber quem NÃO foi -- só assim dá pra saber
    sobre quais grupos o primer não permite fazer afirmação nenhuma.

    Fonte dos organismos catalogados: docs/dados/acervo_genomas.json (gerado
    por scripts_auxiliares/exportar_acervo_genomas.py, já descontando a
    curadoria de habitat). Como esse arquivo é uma exportação estática que
    precisa ser regenerada manualmente sempre que novos genomas entram no
    banco (ver README, seção de bugs resolvidos), a lista pode ficar
    levemente desatualizada em relação ao banco de busca "ao vivo" -- por
    isso retorna também um aviso quando isso não pode ser conferido.
    """
    caminho_acervo = os.path.join(raiz_projeto, "docs", "dados", "acervo_genomas.json")
    if not os.path.exists(caminho_acervo):
        return None, "Acervo de genomas (docs/dados/acervo_genomas.json) não encontrado -- não foi possível calcular quem ficou de fora."

    with open(caminho_acervo, "r", encoding="utf-8") as f:
        acervo = json.load(f)

    todos_organismos_do_banco = set()
    for banco in acervo.get("bancos", []):
        if banco.get("id") in grupos_do_banco:
            todos_organismos_do_banco.update(banco.get("organismos", []))

    if not todos_organismos_do_banco:
        return None, "Nenhum dos grupos pesquisados foi encontrado no acervo de genomas -- não foi possível calcular quem ficou de fora."

    nao_capturados = sorted(todos_organismos_do_banco - set(especies_capturadas))
    aviso = None
    gerado_em = acervo.get("gerado_em")
    if gerado_em:
        aviso = f"Lista de organismos do banco conforme acervo_genomas.json (gerado em {gerado_em}) -- pode não refletir genomas adicionados depois dessa data."
    return nao_capturados, aviso


def calcular_cobertura(genomas_capturados, total_genomas_banco):
    """Cobertura estimada = genomas distintos capturados / genomas do banco.

    Mesma unidade dos dois lados: cada sequenciamento (assembly) conta 1 --
    duas montagens diferentes da mesma espécie contam 2, porque o banco também
    as cataloga como 2 genomas. (Histórico: contar espécies dividia espécie
    por genoma e subestimava -- 4.231 / 8.466 = 50% contra 79,5% por genoma;
    contar accessions inflava -- 294 scaffolds de um isolado = "294 genomas".
    Ver taxonomia_local.contar_genomas_distintos.)
    """
    return (genomas_capturados / total_genomas_banco) if total_genomas_banco > 0 else 0


def avisos_do_relatorio(cobertura, mismatches, aviso_nao_capturados=None):
    avisos = []
    if cobertura < COBERTURA_BAIXA:
        avisos.append("Cobertura geral baixa. Verifique os filos relevantes.")
    if mismatches > 2:
        avisos.append("Potenciais off-targets (Tolerância a mismatch alta).")
    if aviso_nao_capturados:
        avisos.append(aviso_nao_capturados)
    return avisos


def montar_resultado(req, req_id, parametros, banco, primers, hits, genomas_capturados,
                     arvore, metadados, papeis_funcionais, nao_capturados, avisos, cobertura):
    """O dicionário do result.json (o formato que docs/template.html espera)."""
    return {
        "request_id": req_id,
        "metadata": {
            "submitted_by": str(req.get('Nome completo', 'Pesquisador')),
            "email": str(req.get('Email', '')),
            "submitted_at": datetime.now().strftime("%d/%m/%Y às %H:%M"),
            "target_region": str(req.get('Região alvo', 'Não informada')),
            "organism": str(req.get('Tipo de organismo', 'Não informado')),
            "max_mismatches": parametros["mismatches"],
            "amplicon_min": int(parametros["min_size"]),
            "amplicon_max": int(parametros["max_size"]),
            "e_value": float(parametros["e_value"]),
            "blast_task": BLAST_TASK,
            "word_size": WORD_SIZE,
            "dbsize": DBSIZE,
            "min_coverage": int(parametros["cobertura"]),
            "max_hits": int(parametros["max_hits"]),
            "min_tm": float(parametros["tm_min"]),
            "database": banco.nome,
        },
        "primers": {
            "forward": primers["forward"],
            "reverse": primers["reverse"],
            "pair_name": primers["pair_name"],
        },
        "summary": {
            "total_sequences_checked": banco.total_genomas,
            "total_matches": hits.total,
            "unique_organisms": genomas_capturados,
            "estimated_coverage": round(cobertura, 5),
            "off_target_matches": 0,
            "mean_amplicon_size": round(hits.media_amplicon, 1),
        },
        "functional_tree": papeis_funcionais,
        "taxonomy_tree": arvore,
        "leaf_metadata": metadados,
        "not_captured_organisms": nao_capturados,
        "warnings": avisos,
    }


def gravar(pasta_resultado, resultado, sequencias_completas, raiz_projeto):
    """Grava result.json, sequencias_completas.json (se houver) e a página (index.html)."""
    print("📝 Salvando arquivos de saída (JSON/HTML)...")
    with open(os.path.join(pasta_resultado, "result.json"), 'w', encoding='utf-8') as f:
        json.dump(resultado, f, ensure_ascii=False, separators=(',', ':'))

    # Sequências que não couberam no result.json: o botão "Baixar FASTA" busca
    # este arquivo só quando clicado (a página continua 100% estática).
    if sequencias_completas:
        with open(os.path.join(pasta_resultado, "sequencias_completas.json"), 'w', encoding='utf-8') as f:
            json.dump(sequencias_completas, f, ensure_ascii=False, separators=(',', ':'))

    shutil.copy(os.path.join(raiz_projeto, "docs/template.html"), os.path.join(pasta_resultado, "index.html"))
