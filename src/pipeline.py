"""
A análise de um pedido, do começo ao fim (run_pipeline), usada pelos dois
monitores: main.py (Google Forms/planilha) e main_issues.py (GitHub Issues).
Cada um só lê o pedido do seu jeito e chama run_pipeline(req, req_id, origem).

Etapas de run_pipeline:
  1. valida o pedido (notificacoes.validar_pedido) e escolhe o banco;
  2. roda o BLAST (primer_blast_local.py -> run_parse_blastn.py);
  3. lê os hits, monta as árvores (arvore_taxonomica.py) e calcula a cobertura;
  4. grava docs/reports/<req_id>/ (result.json, index.html, sequências).

Quem publica (vitrine, git, e-mail) é o monitor, depois que run_pipeline termina.
"""
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

import bloqueios
import notificacoes
import taxonomia_local
from arvore_taxonomica import construir_arvore_aninhada


def validate_primer(seq):
    seq = str(seq).strip()
    if not (10 <= len(seq) <= 40): return False
    if not re.match(r"^[ACGTRYSWKMBDHVNacgtryswkmbdhvn]+$", seq): return False
    return True


def extrair_campo_flexivel(dicionario_linha, palavra_chave, padrao="N/A"):
    """ Busca colunas no CSV ignorando maiúsculas/minúsculas """
    for coluna, valor in dicionario_linha.items():
        if coluna and palavra_chave.lower() in coluna.lower():
            return valor
    return padrao


def calcular_organismos_nao_capturados(raiz_projeto, grupos_do_banco, especies_capturadas):
    """
    Retorna a lista de organismos catalogados nos grupos pesquisados que o
    primer NÃO capturou nesta análise (por nome de espécie, mesmo nível do
    "leaf_metadata"/árvore taxonômica -- não é a mesma unidade "por genoma"
    da Cobertura Estimada, ver comentário em total_organismos_unicos acima).

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


def run_pipeline(req, req_id, origem="PEDIDO"):
    """Roda a análise completa de um pedido: valida, roda o BLAST, monta as
    árvores e grava o relatório em docs/reports/<req_id>/.

    req: o pedido já em português (chaves "Primer forward", "Banco de Dados"...).
    origem: só para o log ("PLANILHA" no main.py, "ISSUE" no main_issues.py).

    Devolve (caminho_relativo_do_relatorio, resultado_json).
    """
    # Confere o pedido antes de qualquer BLAST: o que o usuário pode corrigir
    # (primer inválido, número fora do formato...) volta pra ele com a lista.
    problemas = notificacoes.validar_pedido(req)
    if problemas:
        raise notificacoes.PedidoInvalido(problemas)

    raiz_projeto = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    pasta_resultado = os.path.join(raiz_projeto, f"docs/reports/{req_id}")
    os.makedirs(pasta_resultado, exist_ok=True)
    
    fwd = str(req.get('Primer forward', '')).strip().upper()
    rev = str(req.get('Primer reverse', '')).strip().upper()
    alvo_para_nome = str(req.get('Região alvo', '')).strip()
    nome_par = str(req.get('Nome do Par de Primers', '')).strip()
    if not nome_par:
        nome_par = f"Par {alvo_para_nome}" if alvo_para_nome else f"Par {req_id}"

    caminho_primer = os.path.join(pasta_resultado, "primer.fasta")
    with open(caminho_primer, "w") as f:
        f.write(f">Ensaio_{req_id}|Target|fwd\n{fwd}\n")
        f.write(f">Ensaio_{req_id}|Target|rev\n{rev}\n")

    min_size = str(req.get('Tamanho do amplicon: MIN', 20) or 20)
    max_size = str(req.get('Tamanho do amplicon: MAX', 9999) or 9999)
    mismatches = int(req.get('Máximo de Mismatches na extremidade 3', 0) or 0)
    e_value = str(req.get('E-value máximo', 10.0) or 10.0)
    cobertura = str(req.get('Cobertura mínima', 0) or 0)
    # Teto de segurança do servidor: em 03/09/2026 uma submissão com
    # "Limite de hits"=30000 + --amp_seq (busca sequência completa do
    # amplicon, 2-8kb "long read", por hit) chegou a consumir ~123GB de RAM
    # numa máquina de 125GB e foi morta pelo OOM killer do Linux -- sem esse
    # teto, qualquer pesquisador digitando um número alto no formulário
    # consegue derrubar o servidor sem querer.
    #
    # Esse OOM antigo era do PYTHON (pareamento fwd x rev O(N²) sem
    # agrupar por sseqid + extração de amplicon completo de TODO hit bruto),
    # não do blastn -- já corrigido em run_parse_blastn.py (agrupamento por
    # genoma, para no 1º par válido, então só ~1 amplicon é extraído por
    # genoma, não por hit). Descobrimos em 17/09/2026 que --max_target_seqs
    # baixo (5000) tem um efeito colateral sério e não intencional: é um
    # teto do PRÓPRIO blastn por CONTIG (não por genoma), aplicado durante a
    # busca -- com bancos combinados grandes (~8.400 genomas), poucos
    # genomas fragmentados podem consumir toda a cota antes do blastn sequer
    # alcançar milhares de outros genomas, sem erro nenhum, só cobertura
    # artificialmente baixa (caso real: 8.466 genomas no banco, só 227
    # cobertos com teto 5000 vs. cobertura muito maior com teto mais alto).
    # Testado manualmente com 30000: pico de ~114GB de RAM (87%) só no
    # blastn (sem --amp_seq rodando junto), terminou sem OOM. Como o blastn
    # roda e termina ANTES da extração de amplicon começar (memória liberada
    # entre as etapas, não acumula), 30000 é aceito como novo teto.
    LIMITE_MAXIMO_HITS = 30000
    # Sempre o maximo: o pesquisador nao escolhe mais o limite de hits (campo tirado do formulario).
    max_hits = str(LIMITE_MAXIMO_HITS)
    tm_min = str(req.get('Temperatura de Melting mínima (Tm)', 0) or 0)

    # ==========================================
    # SELEÇÃO DINÂMICA DO BANCO DE DADOS (ATLAS)
    # ==========================================
    banco_selecionado = str(req.get('Banco de Dados', 'refseqsoil')).strip().lower()
    
    # --- Mapeamento Dinâmico do Banco Completo Local ---
    DIRETORIO_BLAST = os.environ.get(
        "DIRETORIO_BLAST",
        "/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/blast_dbs"
    )
    try:
        indices = [f.split('.')[0] for f in os.listdir(DIRETORIO_BLAST) if f.endswith('.nsq') or f.endswith('.00.nsq')]
        bancos_locais_unicos = sorted(set(indices))
        string_banco_completo = " ".join(os.path.join(DIRETORIO_BLAST, b) for b in bancos_locais_unicos)
    except FileNotFoundError:
        bancos_locais_unicos = []
        string_banco_completo = ""

    # Mapeamento dinâmico EXCLUSIVO para agrupar os Protozoários
    tags_protozoarios = ["amoebozoa", "sar", "discoba", "metamonada"]
    bancos_protozoa = [os.path.join(DIRETORIO_BLAST, b) for b in tags_protozoarios]
    string_protozoa_completo = " ".join(bancos_protozoa)

    # Mapeamento dinâmico EXCLUSIVO para agrupar os Fungos: os 6 filos que o
    # motor de classificação ecológica (classificar_ecologia) já reconhece
    # como "Fungos" -- quando o usuário escolhe "Fungi" no formulário, roda
    # contra os 6 juntos, igual ao grupo "protozoa" acima.
    tags_fungos = [
        "basidiomycota", "ascomycota", "mucoromycota",
        "chytridiomycota", "zoopagomycota", "glomeromycota",
    ]
    bancos_fungos = [os.path.join(DIRETORIO_BLAST, b) for b in tags_fungos]
    string_fungos_completo = " ".join(bancos_fungos)

    # Mapeamento dinâmico EXCLUSIVO para agrupar as Minhocas: oligochaeta
    # (minhocas propriamente ditas) + enchytraeidae (minhocas-brancas,
    # parentes menores da mesma classe Clitellata) -- não existe opção
    # separada de "Enchytraeidae" no formulário, então "Minhocas" cobre as duas.
    tags_minhocas = ["oligochaeta", "enchytraeidae"]
    bancos_minhocas = [os.path.join(DIRETORIO_BLAST, b) for b in tags_minhocas]
    string_minhocas_completo = " ".join(bancos_minhocas)

    # Banco "eucariotos": igual ao refseqsoil completo, mas sem bacteria/
    # archaea. Motivo: bacteria+archaea sozinhos são a maioria do
    # refseqsoil (>90% dos organismos), mas são procariontes -- não tem a
    # região 18S (é gene ribossomal EUCARIÓTICO; procarionte usa 16S). Pra
    # um primer 18S/ITS/28S, incluir bacteria/archaea no denominador da
    # cobertura infla o "total de organismos no banco" com organismos que o
    # primer NUNCA poderia amplificar, mascarando a cobertura real dentro
    # do grupo que o marcador de fato tem capacidade de detectar.
    tags_nao_eucariotos = {"bacteria", "archaea"}
    bancos_eucariotos = [b for b in bancos_locais_unicos if b not in tags_nao_eucariotos]
    string_eucariotos_completo = " ".join(os.path.join(DIRETORIO_BLAST, b) for b in bancos_eucariotos)

    # Contagem REAL de genomas/organismos por grupo, lida do manifesto gerado
    # por scripts_auxiliares/gerar_manifesto_taxid.py (a partir dos
    # assembly_data_report.jsonl reais). Substitui os números fixos que
    # existiam aqui antes -- eles tinham ficado desatualizados: a soma dos
    # 18 grupos individuais (25.195) nem batia com o total combinado do
    # "refseqsoil" (46.190) que deveriam somar. Só cai pro número antigo,
    # abaixo, se o manifesto daquele grupo específico ainda não existir.
    VALORES_ANTIGOS_FALLBACK = {
        "bacteria": 22550, "archaea": 822, "nematoda": 248, "tardigrada": 6,
        "rotifera": 20, "acari": 145, "collembola": 139, "oligochaeta": 25,
        "formicidae": 213, "isopoda": 14, "myriapoda": 68, "enchytraeidae": 8,
        "isoptera": 50, "platyhelminthes": 103, "amoebozoa": 51, "sar": 599,
        "discoba": 111, "metamonada": 23,
        "coleoptera": 612, "gastropoda": 301, "apoidea": 244, "araneae": 111,
        "scorpiones": 9, "pseudoscorpiones": 1,
    }

    def _contagem_real(grupo_taxid):
        real = taxonomia_local.contagem_organismos_grupo(grupo_taxid)
        return real if real is not None else VALORES_ANTIGOS_FALLBACK.get(grupo_taxid, 0)

    total_protozoa = sum(_contagem_real(g) for g in tags_protozoarios)
    total_fungos = sum(_contagem_real(g) for g in tags_fungos)
    total_minhocas = sum(_contagem_real(g) for g in tags_minhocas)
    total_refseqsoil = sum(_contagem_real(g) for g in bancos_locais_unicos)
    total_eucariotos = sum(_contagem_real(g) for g in bancos_eucariotos)

    # Banco "procariotos": bacteria + archaea (marcadores 16S).
    tags_procariotos = ["bacteria", "archaea"]
    string_procariotos_completo = " ".join(os.path.join(DIRETORIO_BLAST, b) for b in tags_procariotos)
    total_procariotos = sum(_contagem_real(g) for g in tags_procariotos)

    # Dicionário: "nome_no_forms": ("arquivo_fasta", "total_real_de_organismos")
    BANCOS_DISPONIVEIS = {
        "fungi": (string_fungos_completo, total_fungos),
        "protozoa": (string_protozoa_completo, total_protozoa),
        "eucariotos": (string_eucariotos_completo, total_eucariotos),
        "procariotos": (string_procariotos_completo, total_procariotos),
        "bacteria": (os.path.join(DIRETORIO_BLAST, "bacteria"), _contagem_real("bacteria")),
        "archaea": (os.path.join(DIRETORIO_BLAST, "archaea"), _contagem_real("archaea")),
        "nematoda": (os.path.join(DIRETORIO_BLAST, "nematoda"), _contagem_real("nematoda")),
        "tardigrada": (os.path.join(DIRETORIO_BLAST, "tardigrada"), _contagem_real("tardigrada")),
        "rotifera": (os.path.join(DIRETORIO_BLAST, "rotifera"), _contagem_real("rotifera")),
        "acari": (os.path.join(DIRETORIO_BLAST, "acari"), _contagem_real("acari")),
        "collembola": (os.path.join(DIRETORIO_BLAST, "collembola"), _contagem_real("collembola")),
        "minhocas": (string_minhocas_completo, total_minhocas),
        "formigas": (os.path.join(DIRETORIO_BLAST, "formicidae"), _contagem_real("formicidae")),
        "isopodes": (os.path.join(DIRETORIO_BLAST, "isopoda"), _contagem_real("isopoda")),
        "miriapodes": (os.path.join(DIRETORIO_BLAST, "myriapoda"), _contagem_real("myriapoda")),
        "enchytraeidae": (os.path.join(DIRETORIO_BLAST, "enchytraeidae"), _contagem_real("enchytraeidae")),
        "isoptera": (os.path.join(DIRETORIO_BLAST, "isoptera"), _contagem_real("isoptera")),
        "cupins": (os.path.join(DIRETORIO_BLAST, "isoptera"), _contagem_real("isoptera")),  # alias -- dropdown do Issue usa "Cupins", não "Isoptera"
        "platelmintos": (os.path.join(DIRETORIO_BLAST, "platyhelminthes"), _contagem_real("platyhelminthes")),
        "coleoptera": (os.path.join(DIRETORIO_BLAST, "coleoptera"), _contagem_real("coleoptera")),
        "gastropoda": (os.path.join(DIRETORIO_BLAST, "gastropoda"), _contagem_real("gastropoda")),
        "apoidea": (os.path.join(DIRETORIO_BLAST, "apoidea"), _contagem_real("apoidea")),
        "araneae": (os.path.join(DIRETORIO_BLAST, "araneae"), _contagem_real("araneae")),
        "scorpiones": (os.path.join(DIRETORIO_BLAST, "scorpiones"), _contagem_real("scorpiones")),
        "pseudoscorpiones": (os.path.join(DIRETORIO_BLAST, "pseudoscorpiones"), _contagem_real("pseudoscorpiones")),
        "amoebozoa": (os.path.join(DIRETORIO_BLAST, "amoebozoa"), _contagem_real("amoebozoa")),
        "sar": (os.path.join(DIRETORIO_BLAST, "sar"), _contagem_real("sar")),
        "discoba": (os.path.join(DIRETORIO_BLAST, "discoba"), _contagem_real("discoba")),
        "metamonada": (os.path.join(DIRETORIO_BLAST, "metamonada"), _contagem_real("metamonada")),
        "basidiomycota": (os.path.join(DIRETORIO_BLAST, "basidiomycota"), _contagem_real("basidiomycota")),
        "ascomycota": (os.path.join(DIRETORIO_BLAST, "ascomycota"), _contagem_real("ascomycota")),
        "mucoromycota": (os.path.join(DIRETORIO_BLAST, "mucoromycota"), _contagem_real("mucoromycota")),
        "chytridiomycota": (os.path.join(DIRETORIO_BLAST, "chytridiomycota"), _contagem_real("chytridiomycota")),
        "zoopagomycota": (os.path.join(DIRETORIO_BLAST, "zoopagomycota"), _contagem_real("zoopagomycota")),
        "glomeromycota": (os.path.join(DIRETORIO_BLAST, "glomeromycota"), _contagem_real("glomeromycota")),
        "refseqsoil": (string_banco_completo, total_refseqsoil)
    }

    # Mesmas chaves de BANCOS_DISPONIVEIS acima, mas apontando pra lista de
    # grupos taxonômicos (não pro caminho/contagem) -- usado só por
    # calcular_organismos_nao_capturados pra saber quais entradas de
    # docs/dados/acervo_genomas.json somar pra cada banco escolhido no forms.
    BANCOS_GRUPOS = {
        "fungi": set(tags_fungos),
        "protozoa": set(tags_protozoarios),
        "eucariotos": set(bancos_eucariotos),
        "procariotos": set(tags_procariotos),
        "bacteria": {"bacteria"},
        "archaea": {"archaea"},
        "nematoda": {"nematoda"},
        "tardigrada": {"tardigrada"},
        "rotifera": {"rotifera"},
        "acari": {"acari"},
        "collembola": {"collembola"},
        "minhocas": set(tags_minhocas),
        "formigas": {"formicidae"},
        "isopodes": {"isopoda"},
        "miriapodes": {"myriapoda"},
        "enchytraeidae": {"enchytraeidae"},
        "isoptera": {"isoptera"},
        "cupins": {"isoptera"},
        "platelmintos": {"platyhelminthes"},
        "coleoptera": {"coleoptera"},
        "gastropoda": {"gastropoda"},
        "apoidea": {"apoidea"},
        "araneae": {"araneae"},
        "scorpiones": {"scorpiones"},
        "pseudoscorpiones": {"pseudoscorpiones"},
        "amoebozoa": {"amoebozoa"},
        "sar": {"sar"},
        "discoba": {"discoba"},
        "metamonada": {"metamonada"},
        "basidiomycota": {"basidiomycota"},
        "ascomycota": {"ascomycota"},
        "mucoromycota": {"mucoromycota"},
        "chytridiomycota": {"chytridiomycota"},
        "zoopagomycota": {"zoopagomycota"},
        "glomeromycota": {"glomeromycota"},
        "refseqsoil": set(bancos_locais_unicos),
    }

    # 1. Busca no dicionário
    if banco_selecionado in BANCOS_DISPONIVEIS:
        arquivo_alvo, total_sequencias_banco = BANCOS_DISPONIVEIS[banco_selecionado]
    else:
        # Antes: caía em silêncio no "refseqsoil" (o maior banco, horas de BLAST) e o
        # usuário não sabia que o banco pedido não existia. Agora volta pra ele.
        raise notificacoes.PedidoInvalido(
            notificacoes.validar_pedido(req, bancos_validos=set(BANCOS_DISPONIVEIS))
            or [(f'Banco de dados "{banco_selecionado}" não reconhecido.', f'Database "{banco_selecionado}" not recognized.')]
        )

    # 2. Resolução do caminho (Lógica Híbrida)
    if " " in arquivo_alvo or arquivo_alvo.startswith("/"):
        caminho_genomas = arquivo_alvo  
    else:
        # Lógica legada para arquivos .fasta soltos (ex: "fungi_all.fasta")
        caminho_genomas = os.path.join(raiz_projeto, "data/refseq", arquivo_alvo)

    prefixo_saida = os.path.join(pasta_resultado, "saida")
    
    
    cmd_blast = [
        sys.executable, "primer_blast_local.py",
        "-g", caminho_genomas, "-p", caminho_primer, "-o", prefixo_saida,
        "-e", e_value, "--min_size", min_size, "--max_size", max_size,
        "-m", tm_min, "--max_3prime_mismatches", str(mismatches),
        "--qcov_hsp_perc", cobertura, "--max_target_seqs", max_hits,
        # -num_threads=1 é proposital: com >1 thread e um banco combinado com
        # bancos "split" em múltiplos volumes (bacteria, ascomycota, sar,
        # platyhelminthes...), o blastn trava com um NULL pointer dentro de
        # BlastFormatter_PreFetchSequenceData/x_RunMTBySplitDB ao buscar as
        # sequências do amplicon (qseq/sseq no outfmt) -- é um bug conhecido
        # do próprio NCBI BLAST+ nessa combinação (multithread + split DB +
        # outfmt pedindo sequência), não um problema dos nossos dados. Rodar
        # com 1 thread evita esse caminho de código. Fica mais lento, mas
        # não trava.
        "-t", "1",
        "--amp_seq"
    ]
    
    print(f"\n🔍 Rodando BLAST ({req_id}) no banco {banco_selecionado}...")
    print("🤖 Comando exato que o Script montou:")
    print(" ".join(cmd_blast))
    print("-" * 50)
	
    print(f"\n🕵️‍♂️ RAIO-X DA {origem} (O que o Python realmente está lendo):")
    for chave, valor in req.items():
        print(f"Coluna: '{chave}' | Valor recebido: '{valor}'")
    print("⚙️ Rodando programa...")
    
    # Banco grande = uma busca por vez em todo o servidor (formulário e Issues
    # juntos); a espera fica FORA do cronômetro.
    with bloqueios.bloqueio_se(total_sequencias_banco >= bloqueios.LIMITE_BANCO_PESADO, "blast-pesado", "⏳ Outra análise com banco grande está rodando; aguardando a vez para não estourar a memória do servidor..."):
        # 1. Inicia o cronômetro
        inicio_blast = time.time()

        subprocess.run(cmd_blast, cwd=raiz_projeto, check=True, capture_output=True, text=True)

        # 2. Para o cronômetro e calcula a diferença
        fim_blast = time.time()
    tempo_total_segundos = fim_blast - inicio_blast
    
    # 3. Formata o tempo para ficar bonito no log (ex: 1m 45s)
    minutos = int(tempo_total_segundos // 60)
    segundos = int(tempo_total_segundos % 60)
    tempo_formatado = f"{minutos}m {segundos}s"
    
    print(f"⏱️ Tempo de execução do banco '{banco_selecionado}': {tempo_formatado}")

    hits_data_map = {}
    arquivo_pass = f"{prefixo_saida}__results.pass.csv"
    total_matches = 0
    soma_amplicon = 0
    # dict usado como conjunto ORDENADO: guarda a ordem do CSV do BLAST. Um set
    # mudaria de ordem a cada execução (hash aleatório de str), e com ele a ordem
    # das árvores e qual accession aparece no card de espécies com várias sequências.
    bacterias_encontradas = {}

    # Limite global (não por espécie) de caracteres de sequência de amplicon
    # guardados DIRETO no result.json. Sem isso, buscas com muitos hits geram
    # um JSON gigante -- já aconteceu de passar dos 145MB, estourando o
    # limite de 100MB por arquivo do GitHub e travando o push do relatório.
    # O corte é só na sequência (o resto do hit -- acc/size/tm/start/end --
    # continua sendo salvo pra TODOS os hits, então nenhuma estatística é
    # perdida, só deixa de ter a sequência completa embutida na página).
    #
    # As sequências que ficam de fora do result.json NÃO são descartadas --
    # vão pra um arquivo separado (sequencias_completas.json, ver mais
    # abaixo) que o botão "Baixar FASTA" busca sob demanda só quando
    # clicado, sem pesar o carregamento inicial da página. Esse arquivo tem
    # orçamento próprio, bem maior (ainda seguro dentro do limite de 100MB
    # do GitHub) -- cobre a esmagadora maioria dos casos reais. No raríssimo
    # caso de estourar os DOIS orçamentos, a sequência realmente não fica
    # disponível pra download (só no servidor de processamento).
    ORCAMENTO_MAX_CARACTERES_SEQ = 15_000_000
    ORCAMENTO_MAX_CARACTERES_SEQ_COMPLETA = 80_000_000
    caracteres_seq_acumulados = 0
    caracteres_completa_acumulados = 0

    if os.path.exists(arquivo_pass):
        with open(arquivo_pass, mode='r', encoding='utf-8') as f:
            leitor = csv.DictReader(f)
            for linha in leitor:
                total_matches += 1
                sid = linha.get('Subject_ID', 'Desconhecido')
                bacterias_encontradas[sid] = None

                size_val = extrair_campo_flexivel(linha, "size", "0")
                try: soma_amplicon += int(size_val)
                except: pass

                if sid not in hits_data_map:
                    hits_data_map[sid] = []

                partes_sid = sid.split('|')
                acc_limpo = partes_sid[1] if len(partes_sid) > 1 and partes_sid[0].lower() in ['gb', 'ref', 'emb', 'dbj', 'gi'] else partes_sid[0]
                acc_limpo = acc_limpo.split('.')[0]

                tm_real = "N/A"
                for chave, valor in linha.items():
                    if chave and "amplicon_tm" in chave.lower().strip():
                        tm_real = valor
                        break

                seq_original = linha.get('Amplicon_sequence', linha.get('amplicon_sequence', 'Sequência indisponível'))
                seq_omitida = False
                seq_completa_disponivel = False
                seq_amplicon = seq_original
                if caracteres_seq_acumulados < ORCAMENTO_MAX_CARACTERES_SEQ:
                    caracteres_seq_acumulados += len(seq_original)
                else:
                    seq_omitida = True
                    if caracteres_completa_acumulados < ORCAMENTO_MAX_CARACTERES_SEQ_COMPLETA:
                        caracteres_completa_acumulados += len(seq_original)
                        seq_completa_disponivel = True
                        seq_amplicon = "Sequência não exibida neste relatório (limite de tamanho do arquivo) — clique em \"Baixar FASTA\" para obtê-la."
                    else:
                        seq_amplicon = "Sequência não incluída neste relatório (limite de tamanho do arquivo atingido) — dados brutos preservados no servidor de processamento."

                hits_data_map[sid].append({
                    "acc": acc_limpo,
                    "size": extrair_campo_flexivel(linha, "size", "N/A"),
                    "tm": tm_real,  # <-- Agora usa o valor cravado!
                    "start": extrair_campo_flexivel(linha, "start", "N/A"),
                    "end": extrair_campo_flexivel(linha, "end", "N/A"),
                    # Tenta pegar as colunas exatas do amplicon primeiro!
                    "seq": seq_amplicon,
                    # Flag explícita pro template.html decidir se oferece o
                    # botão de download -- sem isso, ele baixava esse texto
                    # de aviso formatado como se fosse a sequência real.
                    "omitido": seq_omitida,
                    # Guardada só em memória -- extraída pro arquivo separado
                    # sequencias_completas.json (e removida daqui) antes de
                    # salvar o result.json, ver mais abaixo.
                    "_seq_completa": seq_original if seq_completa_disponivel else None,
                    # Quantos hits BRUTOS do BLAST (fwd+rev, antes de validar Tm/mismatch)
                    # esse genoma teve no total -- calculado em _evaluate_hit_loc
                    # (run_parse_blastn.py), que agora para no 1º par válido por genoma
                    # em vez de esgotar a cota de --max_target_seqs num único genoma
                    # fragmentado/multi-cópia.
                    "raw_hits_genoma": extrair_campo_flexivel(linha, "Raw_hits_no_genoma", "N/A")
                })

    media_amplicon = (soma_amplicon / total_matches) if total_matches > 0 else 0
    lista_bacterias = list(bacterias_encontradas)
    
    print("⚙️ Preparando montagem taxonômica...")
    arvore_real, meta_dict, papeis_funcionais = construir_arvore_aninhada(lista_bacterias, total_matches, hits_data_map)

    # Quantos GENOMAS (sequenciamentos) distintos foram capturados de cada
    # espécie -- o painel "Cobertura por Grupo Taxonômico" do template soma
    # isso por grupo pra mostrar genomas (mesma unidade do topo do relatório)
    # em vez de só contar nomes de espécie.
    for dados_especie in meta_dict.values():
        dados_especie["genomas_capturados"] = taxonomia_local.contar_genomas_distintos(
            [amp["acc"] for amp in dados_especie["amplicons"]]
        )

    organismos_nao_capturados, aviso_nao_capturados = calcular_organismos_nao_capturados(
        raiz_projeto, BANCOS_GRUPOS.get(banco_selecionado, set()), meta_dict.keys()
    )

    # Extrai as sequências completas (guardadas em "_seq_completa") pra um
    # arquivo separado -- sequencias_completas.json -- que o botão "Baixar
    # FASTA" do relatório busca sob demanda quando a sequência não coube no
    # orçamento embutido no result.json. Isso permite baixar a sequência
    # real (não um aviso) mesmo com a página sendo 100% estática, sem
    # precisar de nenhum backend: o arquivo fica publicado no GitHub Pages
    # igual ao result.json, só não é carregado até o usuário clicar.
    sequencias_completas = {}
    for especie, dados in meta_dict.items():
        lista_seqs = [amp.pop("_seq_completa", None) for amp in dados["amplicons"]]
        if any(s is not None for s in lista_seqs):
            sequencias_completas[especie] = lista_seqs

    avisos = []
    # Cobertura = GENOMAS únicos batidos (len(lista_bacterias)) sobre o total
    # de genomas do grupo (total_sequencias_banco) -- mesma unidade dos dois
    # lados. Duas montagens de genoma diferentes da MESMA espécie (ex: dois
    # sequenciamentos distintos de um papagaio) contam como 2 aqui, porque o
    # banco também as cataloga como 2 genomas distintos.
    #
    # Antes (até 10/09) usava len(meta_dict) -- 1 entrada por ESPÉCIE -- só
    # porque na época results.pass.csv ainda tinha 1 linha por CONTIG bruto
    # (várias por organismo em genomas fragmentados), então contar por
    # espécie era o único jeito de aproximar "organismo" sem inflar o
    # numerador. Isso mudou com o agrupamento por genoma em
    # _evaluate_hit_loc (run_parse_blastn.py, ver README) -- desde então
    # results.pass.csv já tem no máximo ~1 linha por GENOMA (não por
    # contig), então len(lista_bacterias) passou a ser a contagem correta
    # de genomas, e usar len(meta_dict) (espécie) voltava a misturar
    # unidades no sentido oposto: dividia espécie por genoma, subestimando a
    # cobertura real (caso observado: 4.231 espécies / 8.466 genomas = 50%
    # exibido, mas o número por genoma, cientificamente o que "quantos
    # genomas catalogados o primer detectou", é 6.735 / 8.466 = 79,5%).
    # meta_dict continua agrupado por espécie só para a árvore taxonômica
    # de navegação (leaf_metadata) -- não para esta estatística de cobertura.
    #
    # ATUALIZAÇÃO: len(lista_bacterias) conta ACCESSIONS (scaffolds/
    # cromossomos), não genomas -- só contigs WGS eram agrupados, então
    # genomas com accessions NW_/NC_/cromossomos contavam várias vezes (ex:
    # 294 scaffolds de um mesmo isolado = "294 genomas"), inflando a
    # cobertura (79,2% contra ~50% por espécie no REQ-20260922-0082). Agora
    # cada sequenciamento (assembly) conta 1 -- ver contar_genomas_distintos.
    total_organismos_unicos = taxonomia_local.contar_genomas_distintos(lista_bacterias)
    cobertura_global = (total_organismos_unicos / total_sequencias_banco) if total_sequencias_banco > 0 else 0
    if cobertura_global < 0.60: avisos.append("Cobertura geral baixa. Verifique os filos relevantes.")
    if mismatches > 2: avisos.append("Potenciais off-targets (Tolerância a mismatch alta).")
    if aviso_nao_capturados: avisos.append(aviso_nao_capturados)

    data_bonita = datetime.now().strftime("%d/%m/%Y às %H:%M")

    resultado_json = {
        "request_id": req_id,
        "metadata": {
            "submitted_by": str(req.get('Nome completo', 'Pesquisador')),
            "email": str(req.get('Email', '')), 
            "submitted_at": data_bonita,
            "target_region": str(req.get('Região alvo', 'Não informada')),
            "organism": str(req.get('Tipo de organismo', 'Não informado')),
            "max_mismatches": mismatches,
            "amplicon_min": int(min_size),
            "amplicon_max": int(max_size),
            "e_value": float(e_value),
            "blast_task": "blastn-short",
            "word_size": 7,
            "dbsize": 1_000_000_000,  # DBSIZE_REFERENCIA de run_parse_blastn.py
            "min_coverage": int(cobertura),
            "max_hits": int(max_hits),
            "min_tm": float(tm_min),
            "database": banco_selecionado
        },
        "primers": {
            "forward": fwd,
            "reverse": rev,
            "pair_name": nome_par
        },
        "summary": {
            "total_sequences_checked": total_sequencias_banco,
            # total_matches (contador de linhas do CSV) e não len(lista_bacterias)
            # (accessions ÚNICAS) -- ver comentário em construir_arvore_aninhada
            # sobre o mesmo tipo de subcontagem na árvore taxonômica.
            "total_matches": total_matches,
            "unique_organisms": total_organismos_unicos,
            "estimated_coverage": round(cobertura_global, 5),
            "off_target_matches": 0,
            "mean_amplicon_size": round(media_amplicon, 1)
        },
        # ---> 2. INJETAR O NOVO NÓ AQUI ANTES DO WARNINGS:
        "functional_tree": papeis_funcionais,
        "taxonomy_tree": arvore_real,
        "leaf_metadata": meta_dict,
        # Organismos catalogados nos grupos pesquisados que o primer NÃO
        # capturou nesta análise (por espécie -- ver comentário em
        # calcular_organismos_nao_capturados acima). None quando não foi
        # possível calcular (acervo_genomas.json ausente/grupo não mapeado).
        "not_captured_organisms": organismos_nao_capturados,
        "warnings": avisos
    }

    print("📝 Salvando arquivos de saída (JSON/HTML)...")
    with open(os.path.join(pasta_resultado, "result.json"), 'w', encoding='utf-8') as f:
        # Sem indent: result.json só é lido por código (JS do relatório), nunca
        # manualmente -- indentado, o mesmo conteúdo pode passar de 2-3x o
        # tamanho por causa dos espaços/quebras de linha repetidos em milhares
        # de entradas. Compacto ajuda a ficar dentro do limite de 100MB por
        # arquivo do GitHub (ver ORCAMENTO_MAX_CARACTERES_SEQ acima, que já
        # limita a maior parte do peso -- as sequências de amplicon).
        json.dump(resultado_json, f, ensure_ascii=False, separators=(',', ':'))

    if sequencias_completas:
        with open(os.path.join(pasta_resultado, "sequencias_completas.json"), 'w', encoding='utf-8') as f:
            json.dump(sequencias_completas, f, ensure_ascii=False, separators=(',', ':'))

    shutil.copy(os.path.join(raiz_projeto, "docs/template.html"), os.path.join(pasta_resultado, "index.html"))
    return f"docs/reports/{req_id}", resultado_json
