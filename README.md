# TerraSeq

Plataforma de validação *in silico* de primers para metabarcoding/eDNA de
solo. Um pesquisador submete um par de primers (via Google Forms ou GitHub
Issues), o servidor roda BLAST contra bancos de genomas curados por grupo
taxonômico, e publica automaticamente um relatório interativo (cobertura
taxonômica, amplicons encontrados, classificação funcional/ecológica) numa
página estática no GitHub Pages.

Nome interno usado no HTML das páginas: "eDNA SoilCheck" (aparece no
`<title>` de `docs/index.html` e `docs/template.html`) -- é o mesmo
projeto, "TerraSeq" é o nome público/do repositório.

Este documento existe pra alguém de fora conseguir assumir o projeto sem
precisar perguntar nada pra quem construiu -- se você é essa pessoa, leia
até o fim antes de tocar em qualquer coisa em produção.

---

## Índice

1. [Visão geral do fluxo](#visão-geral-do-fluxo)
2. [Estrutura do repositório](#estrutura-do-repositório)
3. [Estrutura fora do repositório (servidor)](#estrutura-fora-do-repositório-servidor)
4. [Requisitos e versões](#requisitos-e-versões)
5. [Configuração (.env)](#configuração-env)
6. [Os dois pontos de entrada do pipeline](#os-dois-pontos-de-entrada-do-pipeline)
7. [Passo a passo completo de uma submissão](#passo-a-passo-completo-de-uma-submissão)
8. [Como os bancos de dados são construídos e curados](#como-os-bancos-de-dados-são-construídos-e-curados)
9. [Scripts auxiliares (`scripts_auxiliares/`)](#scripts-auxiliares-scripts_auxiliares)
10. [Operação do dia a dia no servidor](#operação-do-dia-a-dia-no-servidor)
11. [Decisões de design e bugs já resolvidos (histórico importante)](#decisões-de-design-e-bugs-já-resolvidos-histórico-importante)
12. [Troubleshooting rápido](#troubleshooting-rápido)

---

## Visão geral do fluxo

```
                    ┌─────────────────────┐        ┌──────────────────────┐
                    │  Google Forms        │        │  GitHub Issue         │
                    │  (planilha "Submis-  │        │  (label               │
                    │  soes_Primers_       │        │  "analise-pendente",  │
                    │  Pipeline")           │        │  template             │
                    │                      │        │  solicitacao_         │
                    │                      │        │  analise.yml)         │
                    └──────────┬───────────┘        └───────────┬───────────┘
                               │                                 │
                               ▼                                 ▼
                    ┌─────────────────────┐        ┌──────────────────────┐
                    │  src/main.py          │        │  src/main_issues.py   │
                    │  (loop while True,    │        │  (loop while True,    │
                    │  poll a cada 10s)     │        │  poll a cada 10s)     │
                    └──────────┬───────────┘        └───────────┬───────────┘
                               └────────────┬────────────────────┘
                                            ▼
                          ┌───────────────────────────────┐
                          │ primer_blast_local.py            │
                          │  -> run_parse_blastn.py           │
                          │  -> blastn (BLAST+ 2.17.0)        │
                          │     contra data/blast_dbs/<banco> │
                          └────────────────┬──────────────────┘
                                           ▼
                          ┌───────────────────────────────┐
                          │ Classificação taxonômica/       │
                          │ ecológica (taxonomia_local.py    │
                          │ + REGRAS_CLASSIFICACAO_ECOLOGICA)│
                          └────────────────┬──────────────────┘
                                           ▼
                          ┌───────────────────────────────┐
                          │ docs/reports/<REQ_ID>/           │
                          │  index.html + result.json         │
                          │ (a partir de docs/template.html) │
                          │ + docs/index.html atualizado      │
                          │ (Vitrine Principal)               │
                          └────────────────┬──────────────────┘
                                           ▼
                          ┌───────────────────────────────┐
                          │ git commit + push               │
                          │ (publicar_no_github)             │
                          │  -> GitHub Pages                 │
                          └────────────────┬──────────────────┘
                                           ▼
                          ┌───────────────────────────────┐
                          │ E-mail de notificação            │
                          │ (SMTP) pro pesquisador           │
                          └───────────────────────────────┘
```

Em uma frase: **um script Python fica num loop infinito checando por novas
submissões, e quando acha uma, monta e roda um comando `blastn` contra o
banco de genomas escolhido, transforma a saída em uma árvore taxonômica e
num relatório HTML, publica isso no GitHub Pages e avisa o pesquisador por
e-mail.**

---

## Estrutura do repositório

```
TerraSeq/
├── src/
│   ├── main.py                # Entry point 1: lê da planilha Google Sheets
│   ├── main_issues.py         # Entry point 2: lê de GitHub Issues
│   └── taxonomia_local.py     # Classificação taxonômica 100% local (SQLite + taxdump)
│
├── primer_blast_local.py      # Orquestra UMA rodada de BLAST + parsing (chamado como
│                               # subprocesso por main.py/main_issues.py via "-g"/"-p"/"-o")
├── run_parse_blastn.py        # Monta o comando blastn, faz parsing do outfmt 6,
│                               # pareamento fwd/rev por genoma, checagem de Tm/mismatch
├── reformat.py                 # Lê/valida arquivos de primers (FASTA ou Excel IDT PrimerQuest)
│
├── scripts_auxiliares/         # Scripts de manutenção dos bancos (ver seção própria)
│
├── docs/                       # Publicado como GitHub Pages (branch/pasta servida)
│   ├── index.html              # Página inicial: Vitrine Principal + Acervo de Genomas
│   ├── template.html           # Template do relatório individual (preenchido por
│   │                            # main.py/main_issues.py pra cada REQ_ID)
│   ├── dados/acervo_genomas.json  # Gerado por exportar_acervo_genomas.py
│   └── reports/<REQ_ID>/       # Um relatório publicado por submissão processada
│       ├── index.html
│       ├── primer.fasta
│       ├── result.json
│       └── sequencias_completas.json  # (opcional, se houver sequências grandes)
│
├── data/                       # Dados pesados -- ver seção "fora do repositório"
│   ├── refseq/                 # (gitignored, symlink pro HD externo) genomas brutos .fna
│   ├── blast_dbs/               # (gitignored) bancos BLAST indexados (.nsq/.nin/.nhr...)
│   ├── manifestos/               # (gitignored) SQLite accession->taxId + JSONs auxiliares
│   └── taxdump/                  # (gitignored) taxonomia oficial do NCBI (nodes.dmp/names.dmp)
│
├── .github/ISSUE_TEMPLATE/
│   └── solicitacao_analise.yml  # Formulário da Issue que main_issues.py consome
│
├── .env                        # (gitignored) credenciais e configuração local -- ver .env.example
└── README.md                   # este arquivo
```

### Módulos principais, o que cada um faz de fato

- **`src/main.py`** -- processo de longa duração (`while True: ... time.sleep(10)`).
  A cada iteração, lê a planilha do Google Sheets (via `gspread`), procura
  linhas sem `Status` preenchido, e para cada uma: monta o comando de BLAST
  (`cmd_blast`), roda como subprocesso, lê `saida__results.pass.csv`,
  classifica taxonomicamente/ecologicamente, monta a árvore aninhada,
  gera `docs/reports/<REQ_ID>/index.html` + `result.json` a partir de
  `docs/template.html`, atualiza `docs/index.html` (Vitrine), comita e
  publica no GitHub Pages, e envia e-mail.
- **`src/main_issues.py`** -- mesma lógica, mas a fonte da submissão é uma
  GitHub Issue com a label `analise-pendente` (formulário
  `.github/ISSUE_TEMPLATE/solicitacao_analise.yml`), usando a API REST do
  GitHub (`requests` + `GITHUB_TOKEN`) em vez do Google Sheets. **Os dois
  processos coexistem e podem rodar ao mesmo tempo.**
- **`src/taxonomia_local.py`** -- ver docstring completa no topo do
  arquivo. Resolve a linhagem taxonômica de uma sequência sem consultar o
  NCBI pela rede (usa um manifesto SQLite `accession -> taxId` + a
  taxonomia oficial do NCBI baixada uma vez). Cai pro `Entrez.efetch`
  (rede, lento, rate-limited) só quando uma sequência não está no
  manifesto local.
- **`primer_blast_local.py`** -- CLI que roda UMA análise completa: recebe
  `-g` (caminho do(s) banco(s), pode ser múltiplos separados por espaço),
  `-p` (primers), `-o` (prefixo de saída), e todos os parâmetros
  científicos (e-value, Tm, mismatches, tamanho de amplicon, etc). É
  chamado como subprocesso por `main.py`/`main_issues.py`.
- **`run_parse_blastn.py`** -- onde o `blastn` de fato é invocado
  (`_call_blastn`), e onde a saída tabular (`-outfmt 6`) é parseada e
  pareada: hits *forward* e *reverse* do mesmo primer só formam um
  amplicon válido se caírem na MESMA sequência-alvo (`sseqid`), e a
  validação (Tm, mismatches na extremidade 3', tamanho do amplicon) para
  no primeiro par válido de cada **genoma** (não de cada contig -- ver
  seção de bugs resolvidos) pra não deixar um genoma fragmentado consumir
  toda a busca.

---

## Estrutura fora do repositório (servidor)

**Máquina:** `papoco` (usuário `othin`), ambiente conda `tiago`
(`/home/othin/miniconda3/envs/tiago/bin/python`).

**Caminho raiz do projeto no servidor:**
`/home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/`

Isso é o clone do repositório. Dentro dele:

- **`data/refseq`** -- é um **link simbólico** para um HD externo montado
  em `/media/othin/5ce034a2-c306-41f5-b965-c577615e08b6/pipeline_genoma_refseq`
  (UUID do disco: `5ce034a2-c306-41f5-b965-c577615e08b6`, dispositivo
  `/dev/sda1`, ext4, ~3.7T). **Se depois de reiniciar a máquina esse
  caminho parecer "vazio" ou der `No such file or directory` mesmo com o
  link existindo, o HD provavelmente não foi remontado automaticamente.**
  Monte com:
  ```bash
  sudo mkdir -p /media/othin/5ce034a2-c306-41f5-b965-c577615e08b6
  sudo mount UUID=5ce034a2-c306-41f5-b965-c577615e08b6 \
    /media/othin/5ce034a2-c306-41f5-b965-c577615e08b6
  ```
  Guarda os `.fna` brutos baixados do NCBI, organizados por
  `data/refseq/<grupo_taxonomico>/` (ex: `data/refseq/coleoptera/`).
- **`data/blast_dbs`** -- fica no disco principal (`/dev/nvme0n1p2`, ~1.8T,
  costuma estar em ~75-80% de uso). Contém os bancos BLAST já indexados
  (`<grupo>.nsq`/`.nin`/`.nhr`/... ou, se o banco for grande, `<grupo>.NN.nsq`
  em múltiplos volumes -- ver seção de bugs resolvidos sobre o limite de
  volumes).
- **`data/manifestos`** e **`data/taxdump`** -- também no disco principal,
  pequenos (poucos GB). Gerados/baixados por `taxonomia_local.py` e
  `gerar_manifesto_taxid.py`.
- **`src/credentials.json`** -- credenciais da service account do Google
  (Sheets + Drive), gitignored. Necessário pra `main.py`.
- **`.env`** -- ver seção de configuração abaixo.

**⚠️ Sobre o processo em si:** não existe (até a data deste documento) um
serviço systemd/cron mantendo `main.py`/`main_issues.py` no ar
permanentemente -- eles são rodados **manualmente**, num terminal, e
ficam vivos enquanto esse terminal/sessão SSH existir. Isso já causou
confusão em investigações (achar que "está rodando" quando na verdade
ninguém iniciou o processo depois do último reboot/logout). Se for
formalizar isso, um serviço systemd de usuário com `Restart=on-failure` é
o caminho natural -- **não existe ainda**, é uma melhoria pendente.

---

## Requisitos e versões

| Componente | Versão usada em produção | Observação |
|---|---|---|
| Python | ambiente conda `tiago` (`/home/othin/miniconda3/envs/tiago/`) | não há `environment.yml`/`requirements.txt` no repo ainda -- ver nota abaixo |
| BLAST+ | **2.17.0+** em `/home/othin/blast-latest/bin/` | ⚠️ existe TAMBÉM uma 2.12.0+ em `/usr/bin/blastn` no mesmo servidor -- **nunca deixe o código depender do `PATH` pra escolher qual usar**. `run_parse_blastn.py` já resolve isso via `CAMINHO_BLAST_BIN` (constante/env var), sempre apontando pro caminho absoluto do 2.17.0. Ver seção de bugs resolvidos. |
| NCBI `datasets` CLI | usado para baixar genomas (`datasets download genome taxon ...` + `datasets rehydrate`) | instalado globalmente no servidor |
| Bibliotecas Python | `gspread`, `google-auth` (`google.oauth2.service_account`), `biopython` (`Bio.Seq`, `Bio.SeqUtils.MeltingTemp`, `Bio.Entrez`, `Bio.Data.IUPACData`), `numpy`, `pandas`, `python-dotenv`, `requests` | sem lockfile formal -- recomendado gerar um `requirements.txt`/`environment.yml` a partir do ambiente `tiago` na próxima manutenção |

**Nota sobre a ausência de `requirements.txt`:** o projeto nunca teve um
arquivo de dependências versionado. Pra reproduzir o ambiente do zero,
rode `pip freeze > requirements.txt` dentro do ambiente conda `tiago` no
servidor e adicione esse arquivo ao repositório -- é uma dívida técnica
conhecida, não um esquecimento deste documento.

---

## Configuração (`.env`)

O arquivo `.env` **não é versionado** (está no `.gitignore`). Crie um a
partir do modelo `.env.example` (na raiz do repo) e preencha os valores
reais. Variáveis usadas:

| Variável | Obrigatória? | Usada por | Descrição |
|---|---|---|---|
| `ENTREZ_EMAIL` | ✅ sim | main.py, main_issues.py | E-mail exigido pela API Entrez do NCBI (fallback quando o manifesto local não tem a sequência) |
| `EMAIL_REMETENTE` | ✅ sim | main.py, main_issues.py | Conta de e-mail que envia a notificação de "relatório pronto" |
| `EMAIL_SENHA` | ✅ sim | main.py, main_issues.py | Senha/senha de app da conta acima |
| `GITHUB_TOKEN` | ✅ sim (só p/ main_issues.py) | main_issues.py | Token com permissão de leitura/escrita em Issues do repositório |
| `SMTP_SERVER` | não (default `smtp.gmail.com`) | ambos | Servidor SMTP de envio |
| `SMTP_PORT` | não (default `587`) | ambos | Porta SMTP |
| `GITHUB_REPO_OWNER` | não (default `TerraSeq`) | ambos | Owner do repo, usado pra montar o link do relatório no e-mail e pra publicar no Pages |
| `GITHUB_REPO_NAME` | não (default `pipeline_genoma` em main.py, `TerraSeq` em main_issues.py ⚠️) | ambos | Nome do repositório -- **os defaults dos dois scripts são diferentes entre si**, confira se isso é intencional antes de mudar um sem o outro |
| `GOOGLE_CREDENTIALS_PATH` | não (default `credentials.json`, relativo a `src/`) | main.py | Caminho do JSON de credenciais da service account do Google |
| `NOME_DA_PLANILHA` | não (default `Submissoes_Primers_Pipeline`) | main.py | Nome da planilha Google Sheets consultada |
| `DIRETORIO_BLAST` | não (default hardcoded pro caminho do servidor) | main.py, main_issues.py | Onde ficam os bancos BLAST indexados (`data/blast_dbs`) |
| `CAMINHO_BLAST_BIN` | não (default `/home/othin/blast-latest/bin`) | run_parse_blastn.py, primer_blast_local.py | Pasta com os binários `blastn`/`makeblastdb`/`blastdbcmd` corretos (2.17.0) -- **sempre caminho absoluto, nunca depende do `PATH`** |

---

## Os dois pontos de entrada do pipeline

O TerraSeq aceita submissões por **dois canais independentes**, que rodam
em paralelo e publicam no mesmo `docs/reports/`:

1. **Google Forms → Google Sheets → `src/main.py`**
   O formulário do Google escreve uma linha na planilha
   `Submissoes_Primers_Pipeline`. `main.py` faz polling nessa planilha
   (via `gspread`) a cada 10 segundos, processa linhas com `Status` vazio,
   e marca como processada ao terminar.

2. **GitHub Issue → `src/main_issues.py`**
   O formulário é `.github/ISSUE_TEMPLATE/solicitacao_analise.yml` (label
   automática `analise-pendente`). `main_issues.py` faz polling na API
   REST do GitHub a cada 10 segundos, procurando Issues abertas com essa
   label, processa e depois fecha/relabela a Issue.

Os dois processos compartilham toda a lógica de negócio (classificação
ecológica, geração de relatório, publicação, e-mail) -- são
implementações quase idênticas, cada uma lendo de uma fonte diferente.
**Isso significa que uma correção de bug ou mudança de comportamento
científico (ex: parâmetros do BLAST, regras de classificação) precisa ser
replicada manualmente nos dois arquivos** -- não há um módulo compartilhado
entre eles hoje. Se for refatorar, extrair a lógica comum pra um módulo
importado por ambos é a melhoria mais valiosa que dá pra fazer nesse
código.

---

## Passo a passo completo de uma submissão

1. **Submissão**: pesquisador preenche o formulário (Forms ou Issue) com:
   nome, e-mail, par de primers (fwd/rev), nome do par, região alvo, tipo
   de organismo, banco de dados a pesquisar, e os parâmetros científicos
   (mismatches máx. na extremidade 3', tamanho min/max do amplicon, Tm
   mínima, e-value máximo, cobertura mínima, limite de hits).
2. **Detecção**: o loop (`main.py` ou `main_issues.py`) encontra a nova
   linha/Issue na próxima iteração do polling (até 10s de atraso).
3. **Preparação**: os primers são escritos em `docs/reports/<REQ_ID>/primer.fasta`.
   O nome do banco escolhido é resolvido contra o dicionário
   `BANCOS_DISPONIVEIS` (mapeia nome amigável -> caminho(s) real(is) em
   `data/blast_dbs/`, que pode ser um único banco ou vários combinados
   via string com espaço, ex: `"acari amoebozoa apoidea ..."`).
4. **BLAST**: `primer_blast_local.py` é chamado como subprocesso com todos
   os parâmetros. Internamente:
   - `run_parse_blastn._call_blastn` monta e roda o `blastn` de fato
     (`-task blastn-short`, `-word_size 7`, `-dbsize` fixo pra e-value
     consistente entre bancos de tamanhos diferentes, `-max_target_seqs`
     limitado a **30000** como teto de segurança contra OOM independente
     do que o usuário pediu -- ver seção de bugs resolvidos: esse teto é
     por CONTIG dentro do próprio `blastn`, não por genoma, e um valor
     baixo demais corta a busca antes de alcançar boa parte de um banco
     combinado grande, mesmo sem nenhum erro).
   - `_blast_to_dict` agrupa os hits por sequência-alvo (`sseqid`).
   - `_evaluate_hit_loc` cruza hits *forward*/*reverse* da mesma
     sequência, agrupa por **genoma** (heurística de prefixo de accession
     WGS) e para no primeiro par válido de cada genoma -- evita que um
     genoma fragmentado/multi-cópia consuma toda a validação.
   - Se `--amp_seq` estiver ativo, `extrair_amplicons_via_blastdbcmd`
     (em `primer_blast_local.py`) busca a sequência completa do amplicon
     via `blastdbcmd`.
   - Saída: `docs/reports/<REQ_ID>/saida__results.pass.csv` (hits que
     passaram todos os filtros) e `saida__results.all.csv` (diagnóstico).
5. **Classificação**: `main.py`/`main_issues.py` lê o `.pass.csv`, agrupa
   por organismo via `taxonomia_local.taxid_por_accession` +
   `linhagem_por_taxid` (cai pro Entrez só se a sequência não estiver no
   manifesto local), monta a árvore taxonômica aninhada e a árvore
   funcional (`classificar_ecologia`, baseada nos 4 grupos funcionais do
   Global Soil Biodiversity Atlas, cap. IV).
6. **Relatório**: `docs/template.html` é preenchido com os dados
   (JavaScript embutido lê `result.json`) e salvo em
   `docs/reports/<REQ_ID>/index.html` + `result.json`. Sequências de
   amplicon muito grandes são orçadas (`ORCAMENTO_MAX_CARACTERES_SEQ`)
   pra não estourar o limite de 100MB por arquivo do GitHub -- o excesso
   vai pra `sequencias_completas.json` ou é omitido, com aviso no relatório.
7. **Vitrine**: `docs/index.html` é atualizado (adiciona a nova submissão
   à lista/carrossel da página inicial).
8. **Publicação**: `publicar_no_github` faz `git add`, `git commit`, `git
   push` da pasta `docs/` -- o GitHub Pages serve o conteúdo
   automaticamente a partir daí (isso é o que faz aparecerem os commits
   automáticos "Report REQ-..." no histórico do repositório).
9. **Notificação**: e-mail enviado via SMTP com o link do relatório
   (`https://<owner>.github.io/<repo>/reports/<REQ_ID>/`).

---

## Como os bancos de dados são construídos e curados

Cada grupo taxonômico (ex: `coleoptera`, `nematoda`, `acari`...) segue este
ciclo de vida:

1. **Estimativa de espaço** (`estimar_espaco_grupos_faltantes.py`) --
   baixa só os metadados (leve) e estima o tamanho total em GB antes de
   comprometer disco com o download pesado.
2. **Download** (`baixar_banco_grupos_faltantes.py`, `baixar_banco_solo.py`
   ou `baixar_banco_fungos.py`, dependendo do grupo) -- usa `datasets
   download genome taxon <grupo> --reference --dehydrated` (metadados) +
   `datasets rehydrate` (sequências de fato) pra `data/refseq/<grupo>/`.
   Retomável se cair no meio.
3. **Manifesto de taxonomia** (`gerar_manifesto_taxid.py`) -- cruza
   `assembly_data_report.jsonl` com os cabeçalhos `.fna` pra gerar o
   SQLite `accession -> taxId` usado por `taxonomia_local.py`.
4. **Levantamento de organismos** (`listar_organismos_por_grupo.py`) --
   gera um CSV com todos os organismos distintos baixados, pra revisão
   manual de curadoria.
5. **Detecção de habitat suspeito** (`detectar_habitat_suspeito.py`) --
   vasculha metadados de BioSample procurando indícios de habitat
   NÃO-terrestre (marinho, água doce). **Não é uma classificação
   completa** -- ausência de indício não prova que o organismo é de solo,
   só que a checagem automática não achou sinal (a maioria dos genomas
   não preenche esses campos).
6. **Curadoria manual** (`curar_bancos.py`, dicionários `TAXIDS_EXCLUIDOS`/
   `ACCESSIONS_EXCLUIDAS`) -- depois de revisar os CSVs dos passos 4/5,
   organismos fora de escopo são listados aqui e o banco é reindexado
   sem eles.
7. **Indexação** (`preparar_blast.py`) -- concatena todos os `.fna` do
   grupo, purifica os cabeçalhos (mantém só o accession), e roda
   `makeblastdb -dbtype nucl -parse_seqids -max_file_sz 3900MB`. **Pula
   automaticamente** qualquer grupo que já tenha `.nsq`/`.00.nsq` em
   `data/blast_dbs/` -- pra forçar reconstrução, apague os arquivos do
   grupo primeiro.
8. **Exportação pro site** (`exportar_acervo_genomas.py`) -- gera
   `docs/dados/acervo_genomas.json` a partir do CSV de organismos, **já
   descontando a curadoria** (importa `TAXIDS_EXCLUIDOS`/
   `ACCESSIONS_EXCLUIDAS` direto de `curar_bancos.py` como fonte única
   de verdade).

**Bancos combinados** (ex: `"eucariotos"`, `"refseqsoil"`) não são um banco
físico único -- são resolvidos em tempo de busca em `main.py`
(`BANCOS_DISPONIVEIS`) como uma string de múltiplos caminhos separados
por espaço, passada direto pro `-db` do `blastn`.

**⚠️ Por que `-max_file_sz 3900MB` (e não o padrão) importa de verdade:**
ver a seção de bugs resolvidos abaixo -- sem isso, um banco grande o
suficiente (>90-100 volumes no formato padrão de ~1GiB/volume) faz o
`blastn` devolver `sseqid="Unknown"` pra 100% dos hits, silenciosamente,
sem erro.

---

## Scripts auxiliares (`scripts_auxiliares/`)

| Script | O que faz |
|---|---|
| `estimar_espaco_grupos_faltantes.py` | Estima em GB o tamanho de grupos ainda não baixados, sem baixar as sequências |
| `baixar_banco_grupos_faltantes.py` | Baixa (dehydrate + rehydrate) os grupos de invertebrados faltantes do Atlas |
| `baixar_banco_solo.py` | Baixa os grupos "leves" (<100GB) |
| `baixar_banco_fungos.py` | Baixa fungos divididos por filo (em vez do reino Fungi inteiro) |
| `gerar_manifesto_taxid.py` | Gera o manifesto SQLite `accession -> taxId/descrição/tamanho` usado por `taxonomia_local.py` |
| `listar_organismos_por_grupo.py` | Gera CSV com organismos distintos por grupo, pra revisão de curadoria |
| `detectar_habitat_suspeito.py` | Sinaliza genomas com metadado de habitat não-terrestre |
| `curar_bancos.py` | Remove organismos fora de escopo (`TAXIDS_EXCLUIDOS`/`ACCESSIONS_EXCLUIDAS`) e reindexa |
| `preparar_blast.py` | Indexa (`makeblastdb`) qualquer grupo baixado que ainda não tenha banco BLAST |
| `exportar_acervo_genomas.py` | Gera `docs/dados/acervo_genomas.json` pra Vitrine/Acervo do site |
| `encolher_result_json.py` | Aplica retroativamente o orçamento de tamanho de sequência a um `result.json` já publicado que passou de 100MB |
| `resumo_bancos.py` | Mostra tabela resumo (genomas/GB) de um conjunto de grupos, direto da API do NCBI, sem baixar nada |

---

## Operação do dia a dia no servidor

**Rodar o pipeline** (dentro do ambiente conda `tiago`):
```bash
cd /home/othin/Documents/tiago/Projeto_completo/pipeline_genoma
conda activate tiago
python3 src/main.py        # canal Google Sheets
# e/ou, em outro terminal:
python3 src/main_issues.py # canal GitHub Issues
```
Ambos ficam em loop infinito (`Ctrl+C` pra parar). Não há restart
automático em caso de crash -- se o terminal fechar ou o processo morrer,
ninguém processa novas submissões até alguém notar e rodar de novo.

**Antes de rodar, sempre confirme:**
```bash
mount | grep 5ce034a2          # HD externo (data/refseq) montado?
df -h /home/othin/Documents/tiago/Projeto_completo/pipeline_genoma/data/blast_dbs  # espaço no disco principal
/home/othin/blast-latest/bin/blastn -version   # deve mostrar 2.17.0+
```

**Adicionar/curar um novo grupo taxonômico:** siga o ciclo de vida
descrito na seção anterior, passo a passo, na ordem.

---

## Decisões de design e bugs já resolvidos (histórico importante)

Registrado aqui pra ninguém perder tempo redescobrindo o mesmo problema.

- **BLAST+ 2.12.0 crashava (NULL pointer, `BlastFormatter_
  PreFetchSequenceData`/`x_RunMTBySplitDB`) em bancos split multi-volume +
  saída pedindo sequência.** Fix real: atualizar pra 2.17.0 (instalado em
  `/home/othin/blast-latest/`, **não** em `/usr/bin`). Trocar thread count
  (`-t`) **não** resolve esse bug -- foi testado e confirmado.

- **Mesmo na 2.17.0, um banco com muitos volumes (>~90-106, exato limite
  não documentado pela NCBI) faz o `blastn` devolver `sseqid="Unknown"`,
  coordenadas zeradas e `sstrand="N/A"` pra 100% dos hits, SEM erro
  fatal** -- só um aviso em stderr (`Error pre-fetching sequence data`)
  que é fácil de não notar porque o processo termina com exit code 0.
  Isso foi diagnosticado por bissecção (dividir os bancos combinados até
  isolar o culpado) depois que o "eucariotos" (28 bancos combinados)
  passou a devolver 0 resultados: o culpado era o banco `coleoptera`
  isolado, com 421GB em 107 volumes (padrão de ~1GiB/volume do
  `makeblastdb`). Bancos com menos volumes (araneae: 70, gastropoda: 89)
  funcionavam normalmente. Fix: `-max_file_sz 3900MB` (o maior valor que
  o `makeblastdb` aceita -- ele recusa qualquer valor ≥ 4GiB) em
  `preparar_blast.py`/`curar_bancos.py`, reduzindo drasticamente o número
  de volumes de qualquer banco futuro. **Se um banco muito grande no
  futuro voltar a dar esse sintoma, o próximo passo é reindexar com um
  `-max_file_sz` menor ainda (mais volumes teria sido pior, então na
  verdade o oposto: confirme quantos volumes ele tem com
  `ls <banco>.*.nsq | wc -l` e compare com o limite observado aqui).**

- **`_evaluate_hit_loc` cruzava TODO hit *forward* com TODO hit *reverse*
  antes de checar se pertenciam à mesma sequência** -- com bancos grandes
  e e-value permissivo, isso gerava produto cartesiano de bilhões de
  combinações e já causou OOM kill (>120GB de RSS do processo Python, não
  do `blastn`). Fix: `_blast_to_dict` indexa por `sseqid` primeiro,
  cruzando só hits que já caem na mesma sequência.

- **Um genoma fragmentado (muitos contigs) com gene multi-cópia (ex:
  rRNA) consumia toda a validação e a cota de `-max_target_seqs`
  desproporcionalmente.** Fix: agrupamento por genoma (heurística de
  prefixo de accession WGS) + parada no primeiro par válido por genoma,
  preservando a contagem BRUTA de hits daquele genoma (coluna
  `Raw_hits_no_genoma`) mesmo com a parada antecipada.

- **`construir_arvore_aninhada` fazia uma chamada `Entrez.efetch` +
  `sleep(0.4s)` por CONTIG único** (não por organismo) -- gargalo de tempo
  gigante em bancos com genes multi-cópia mesmo sendo "pequenos" em
  número de organismos. Fix real: `taxonomia_local.py` (manifesto SQLite
  local + taxdump em memória), Entrez só como fallback raro. Bônus:
  quando o fallback é necessário, é feito em lote (`efetch` com múltiplos
  IDs por chamada) em vez de um por vez.

- **`--max_target_seqs` compartilhado entre bancos combinados
  silenciosamente subestimava a cobertura em bancos grandes.** É um teto
  do PRÓPRIO `blastn`, por CONTIG, aplicado durante a busca em si (não
  algo que o código Python controla depois). Bancos combinados (ex:
  "eucariotos", 28+ grupos) eram passados como uma ÚNICA string
  `-db "path1 path2 ..."` pro `blastn` -- ou seja, todos os bancos
  disputavam a MESMA cota. Com o banco crescendo pra ~8.400 genomas, o
  `blastn` batia no teto (fwd e rev, cada um separadamente) bem antes de
  alcançar a maioria dos genomas -- sem erro nenhum, só devolvendo
  pouquíssimos hits reais (caso observado: 8.466 genomas no banco, só 227
  cobertos com teto 5000). O agrupamento por genoma (`_evaluate_hit_loc`)
  não resolve isso sozinho: ele só otimiza o que o `blastn` já decidiu
  reportar, não recupera dados que o `blastn` nunca chegou a examinar.
  Diagnosticado contando `sseqid`/genoma distintos no `saida__blastn.out`
  bruto e comparando com o valor do teto (bateram exatamente no número
  do teto, nos dois sentidos, tanto com 5000 quanto depois com 30000 --
  ou seja, só subir o número adiava o problema, não resolvia).

  **Fix definitivo**: `_call_blastn` (`run_parse_blastn.py`) agora roda
  um `blastn` SEPARADO por banco (em vez de uma chamada combinada),
  cada um com sua PRÓPRIA cota cheia de `--max_target_seqs`, concatenando
  as saídas num único arquivo antes do parsing -- nenhum banco consegue
  mais "roubar" cota de outro, e isso escala sozinho conforme mais bancos
  forem adicionados na curadoria futura, sem precisar reajustar
  `max_target_seqs` de novo. Bancos únicos (não combinados) continuam se
  comportando exatamente como antes. `LIMITE_MAXIMO_HITS` (`main.py` e
  `main_issues.py` -- esse último não tinha teto nenhum antes, corrigido
  junto) ficou em **30000** como teto POR BANCO (não mais compartilhado),
  validado sem OOM (pico de ~114GB/87% de RAM rodando um banco grande
  sozinho com esse valor).

- **Extração de sequência do amplicon (`blastdbcmd`) uma chamada por hit
  era o novo gargalo depois do fix acima.** Resolvida a cobertura (ex:
  6.735 organismos passando de verdade numa submissão real), a próxima
  etapa -- extrair a sequência do amplicon de cada hit passante via
  `blastdbcmd` -- rodava UMA chamada de subprocesso POR LINHA do CSV de
  resultados, cada chamada reabrindo do zero os 28 bancos combinados do
  alias. Medido em produção: ~1 extração a cada 2,7s, o que pra 6.735
  hits extrapolava pra **~5 horas** só nessa etapa (a submissão real
  REQ-20260918-0069 foi cancelada em andamento por causa disso).

  **Fix**: `extrair_amplicons_via_blastdbcmd` (`primer_blast_local.py`)
  agora monta um arquivo temporário com uma linha `<accession> <range>
  <strand>` por hit e chama `blastdbcmd -entry_batch <arquivo>` UMA ÚNICA
  VEZ pra todos os hits, em vez de um `-entry` por hit (o
  `-entry_batch` aceita exatamente esse formato por linha, confirmado no
  `-help` do binário). Os bancos são abertos uma vez só. Segurança: como
  o alinhamento das sequências de volta pras linhas do CSV é por
  POSIÇÃO (na mesma ordem do arquivo de lote), o código confere se o
  número de linhas devolvidas bate com o número de entradas pedidas
  antes de confiar nesse alinhamento -- se não bater (ex: o
  `blastdbcmd` pulou alguma entrada silenciosamente), cai automaticamente
  pro modo antigo (uma chamada por hit, mais lento mas sempre
  corretamente alinhado) em vez de arriscar associar a sequência errada
  à linha errada. Linhas com coordenadas inválidas (`start`/`end` <= 0)
  continuam sendo puladas do lote e marcadas `N/A` direto, como antes.
  Confirmado em produção (REQ-20260918-0069, reprocessado): blastn levou
  13m13s e o processamento inteiro (extração + árvore taxonômica +
  publicação + e-mail) terminou sem a espera de ~5h de antes.

- **"Cobertura Estimada" e "Organismos Únicos" do relatório misturavam
  unidades (espécie vs. genoma), subestimando a cobertura real.** O
  numerador (`total_organismos_unicos`) vinha de `len(meta_dict)` --
  agrupamento por NOME DE ESPÉCIE via linhagem taxonômica do NCBI -- mas o
  denominador (`total_sequencias_banco`, de `BANCOS_DISPONIVEIS`) conta
  GENOMAS/assemblies cadastrados no banco, não espécies. Se duas
  montagens de genoma diferentes no banco são da mesma espécie (ex: dois
  sequenciamentos distintos de um mesmo tipo de organismo), ambas
  aparecem como hits distintos, mas colapsavam em 1 só no numerador --
  caso observado: REQ-20260918-0069 mostrava "4.231 Organismos Únicos" /
  "8.466 genomas" = 50,0%, enquanto a contagem por genoma (a que já
  tínhamos validado manualmente) era 6.735/8.466 = 79,5%. Esse cálculo
  por espécie fazia sentido quando foi escrito (25/08): na época
  `results.pass.csv` ainda tinha 1 linha por CONTIG bruto (sem
  agrupamento por genoma), então contar por espécie era o único jeito de
  aproximar "organismo" sem inflar o numerador com contigs fragmentados
  do mesmo genoma. Isso mudou com o agrupamento por genoma em
  `_evaluate_hit_loc` (10/09, ver entrada acima sobre
  `--max_target_seqs`) -- desde então `results.pass.csv` já tem no máximo
  ~1 linha por GENOMA, não por contig, então `len(lista_bacterias)`
  (contagem de `Subject_ID` únicos) passou a ser a contagem correta de
  genomas.

  **Fix**: `total_organismos_unicos` em `run_pipeline` (`main.py` e
  `main_issues.py`) agora usa `len(lista_bacterias)` (genoma) em vez de
  `len(meta_dict)` (espécie) pras estatísticas de cobertura. O próprio
  texto do template (`docs/template.html`) já dizia "X de Y **genomas**
  captados" -- confirmando que a unidade esperada sempre foi genoma, só o
  cálculo por trás estava em espécie. `meta_dict` continua agrupado por
  espécie normalmente, só não pra essa estatística -- a árvore
  taxonômica de navegação (`leaf_metadata`) não muda.

- **"Genomas no Banco (Grupo)" (o denominador da Cobertura Estimada)
  contava genomas que já tinham sido removidos pela curadoria de
  habitat -- inflando o denominador com genomas que o BLAST nunca
  consegue achar.** `data/blast_dbs` (o banco de fato pesquisado) é
  construído por `curar_bancos.py`, que exclui organismos fora de escopo
  (`TAXIDS_EXCLUIDOS` -- ex: amebas marinhas, isópodes parasitas de
  peixe) antes de indexar. A Vitrine (`exportar_acervo_genomas.py`) já
  aplicava essa mesma exclusão antes de somar. Mas
  `gerar_manifesto_taxid.py` (gera `contagem_organismos.json`, que
  alimenta `BANCOS_DISPONIVEIS` em `main.py`/`main_issues.py`) contava
  os genomas direto de `data/refseq` (o download bruto, pré-curadoria),
  sem aplicar `TAXIDS_EXCLUIDOS` -- caso observado: banco "eucariotos"
  mostrava 8.466 genomas no relatório, mas a Vitrine (corretamente
  curada) mostrava só 8.369 pro mesmo conjunto de grupos, uma diferença
  de 97 genomas que na prática não existem mais no banco pesquisável.

  **Fix**: `_carregar_info_por_genoma` (`gerar_manifesto_taxid.py`) agora
  importa `TAXIDS_EXCLUIDOS` de `curar_bancos.py` (mesmo padrão já usado
  em `exportar_acervo_genomas.py`) e descarta genomas com taxId banido
  antes de contar E antes de entrar no manifesto SQLite de taxonomia --
  `contagem_organismos.json` passa a refletir o total real de
  `data/blast_dbs`, não o total bruto de `data/refseq`. Rodar
  `gerar_manifesto_taxid.py` de novo no servidor pra regenerar
  `contagem_organismos.json` com os números corretos (não precisa rodar
  `exportar_acervo_genomas.py` de novo -- a Vitrine já estava certa).

- **`data/refseq` é um symlink pra um HD externo que precisa ser montado
  manualmente depois de reboot** -- se comandos que deveriam achar
  arquivos aí derem "No such type of directory" mesmo com o link
  existindo (`ls -la data/` mostra a seta `->`), é isso. Ver comando de
  mount na seção de estrutura do servidor.

- **Sincronização automática do relatório (`main.py`/`main_issues.py`)
  travava com `fatal: stash failed` / `'data/refseq/.gitkeep' is beyond
  a symbolic link` sempre que o push era rejeitado (branch remota
  avançada) e o script tentava `git pull` sozinho.** Causa: `data/refseq`
  era rastreado no git como uma pasta normal com um `.gitkeep` (truque
  pra manter pasta vazia versionada), mas no servidor real esse caminho
  virou um symlink pro HD externo (ver item acima) -- o índice do git
  ficou com um `.gitkeep` "fantasma" (aparecia como deletado no `git
  status`, e `data/refseq` em si como não rastreado). Qualquer operação
  do git que precisasse mexer nesse caminho (merge com árvore não
  totalmente limpa, autostash) travava tentando atravessar o symlink.
  **Fix**: removido `data/refseq/.gitkeep` do rastreamento
  (`git rm --cached`) e o `.gitignore` passou a ignorar `data/refseq`
  inteiro (era `data/refseq/*` + exceção pro `.gitkeep`) -- esse
  caminho não é mais gerenciado pelo git, só documentado no README como
  etapa manual de setup. Se esse erro voltar a acontecer num clone
  antigo, rodar `git rm --cached data/refseq/.gitkeep` (se o arquivo
  ainda estiver rastreado) resolve.

- **`-max_file_sz` do `makeblastdb` rejeita qualquer valor ≥ 4 GiB**
  (`BLAST options error: max_file_sz must be < 4 GiB`) -- não existe
  "banco de volume único" pra bancos muito grandes por essa via; o
  máximo prático é ~3.9GB/volume.

---

## Troubleshooting rápido

| Sintoma | Causa provável | Onde olhar |
|---|---|---|
| `blastn` sem erro, mas 0 organismos únicos no relatório | Banco com `sseqid="Unknown"` (ver bug de volumes acima) | `grep -c "Unknown" docs/reports/<REQ>/saida__blastn.out` |
| Processo lento em bancos "pequenos" | Fallback pro Entrez (manifesto local não cobre esse banco) ou `-max_target_seqs`/O(N²) não otimizado numa versão antiga do código | confirme que está na versão atual de `run_parse_blastn.py`/`taxonomia_local.py` |
| `git pull` não traz mudanças esperadas | Você pode estar numa branch diferente da que o servidor de fato roda | `git branch --show-current`; produção roda em `main` |
| `data/refseq/<algo>` dá "No such file or directory" | HD externo desmontado | ver seção de estrutura do servidor |
| `makeblastdb`/`blastn` chamando a versão errada | Algum código voltou a depender do `PATH` em vez de `CAMINHO_BLAST_BIN` | `grep -rn "\"blastn\"\|'blastn'" *.py` (deve sempre vir de `CAMINHO_BLAST_BIN`, nunca hardcoded solto) |
| `BLAST options error: max_file_sz must be < 4 GiB` | Tentativa de passar `-max_file_sz` ≥ 4GiB | use no máximo `3900MB` |
| "Too many open files" | `ulimit -n` da sessão está baixo (default 1024) | `main.py`/`main_issues.py` já elevam isso no processo (`resource.setrlimit`) na inicialização; testes manuais via terminal precisam de `ulimit -n 65536` antes |
