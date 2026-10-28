#!/usr/bin/env bash
# Tutorial "Moving Pictures" do QIIME 2 (amplicon-docs.qiime2.org), em etapas,
# para estudar a ferramenta. Comandos copiados do PDF do tutorial (versao 2026.10),
# usando DADA2 (sem a opcao Deblur). NAO foi executado por quem escreveu este
# script: se algum comando falhar, compare com a pagina do tutorial.
#
# Uso (com o ambiente conda do QIIME 2 ja ativado: `conda activate <ambiente>`):
#     bash scripts_auxiliares/qiime2_moving_pictures.sh 1      # uma etapa
#     bash scripts_auxiliares/qiime2_moving_pictures.sh 1 3    # da etapa 1 a 3
#     bash scripts_auxiliares/qiime2_moving_pictures.sh        # lista as etapas
#
# Tudo e gravado em ./qiime2-moving-pictures/ (nao mistura com o projeto).
# Arquivos .qzv: abra em https://view.qiime2.org (arraste o arquivo para a pagina).
set -euo pipefail

BASE="https://moving-pictures-tutorial.readthedocs.io/en/2026.10/data/moving-pictures"
DIR="qiime2-moving-pictures"

etapas=(
  "1  Metadados e visualizacao dos metadados"
  "2  Baixar e importar as leituras (artefato .qza)"
  "3  Demultiplexar (separar por amostra) e resumir"
  "4  DADA2: limpar erros e gerar tabela + sequencias (o passo lento, ate ~10 min)"
  "5  Resumos da tabela e das sequencias"
  "6  Arvore filogenetica (a parte que o orientador destacou)"
  "7  Diversidade alfa e beta (core-metrics-phylogenetic)"
  "8  Testes de significancia (alfa e beta) e graficos Emperor"
  "9  Rarefacao alfa"
  "10 Taxonomia: treinar o classificador, classificar, grafico de barras"
  "11 Abundancia diferencial (ANCOM-BC)"
)

if [ $# -eq 0 ]; then
  echo "Etapas:"; printf '  %s\n' "${etapas[@]}"; echo; echo "Ex.: bash $0 1 3"; exit 0
fi
ini="$1"; fim="${2:-$1}"

command -v qiime >/dev/null || { echo "qiime nao encontrado: ative o ambiente conda do QIIME 2 antes."; exit 1; }
mkdir -p "$DIR"; cd "$DIR"

etapa() { [ "$ini" -le "$1" ] && [ "$1" -le "$fim" ]; }
titulo() { echo; echo "=== Etapa $1 ==="; }

if etapa 1; then titulo 1
  wget -O 'sample-metadata.tsv' "$BASE/sample-metadata.tsv"
  qiime metadata tabulate \
    --m-input-file sample-metadata.tsv \
    --o-visualization sample-metadata-viz.qzv
fi

if etapa 2; then titulo 2
  wget -O 'emp-single-end-sequences.zip' "$BASE/emp-single-end-sequences.zip"
  unzip -o -d emp-single-end-sequences emp-single-end-sequences.zip
  qiime tools import \
    --type 'EMPSingleEndSequences' \
    --input-path emp-single-end-sequences \
    --output-path emp-single-end-sequences.qza
fi

if etapa 3; then titulo 3
  qiime demux emp-single \
    --i-seqs emp-single-end-sequences.qza \
    --m-barcodes-file sample-metadata.tsv \
    --m-barcodes-column barcode-sequence \
    --o-per-sample-sequences demux.qza \
    --o-error-correction-details demux-details.qza
  qiime demux summarize \
    --i-data demux.qza \
    --o-visualization demux.qzv
fi

if etapa 4; then titulo 4
  # O tutorial escolhe cortar em 120 bases olhando os graficos de qualidade do demux.qzv.
  qiime dada2 denoise-single \
    --i-demultiplexed-seqs demux.qza \
    --p-trim-left 0 \
    --p-trunc-len 120 \
    --o-representative-sequences rep-seqs.qza \
    --o-table table.qza \
    --o-denoising-stats denoising-stats.qza \
    --o-base-transition-stats base-transition-stats.qza
  qiime metadata tabulate \
    --m-input-file denoising-stats.qza \
    --o-visualization denoising-stats.qzv
fi

if etapa 5; then titulo 5
  qiime feature-table summarize \
    --i-table table.qza \
    --m-metadata-file sample-metadata.tsv \
    --o-summary table.qzv \
    --o-feature-frequencies feature-frequencies.qza \
    --o-sample-frequencies sample-frequencies.qza
  qiime feature-table tabulate-seqs \
    --i-data rep-seqs.qza \
    --o-visualization rep-seqs.qzv
fi

if etapa 6; then titulo 6
  qiime phylogeny align-to-tree-mafft-fasttree \
    --i-sequences rep-seqs.qza \
    --o-alignment aligned-rep-seqs.qza \
    --o-masked-alignment masked-aligned-rep-seqs.qza \
    --o-tree unrooted-tree.qza \
    --o-rooted-tree rooted-tree.qza
fi

if etapa 7; then titulo 7
  # 1103 = profundidade escolhida no tutorial olhando table.qzv (descarta 3 amostras com poucas leituras).
  qiime diversity core-metrics-phylogenetic \
    --i-phylogeny rooted-tree.qza \
    --i-table table.qza \
    --p-sampling-depth 1103 \
    --m-metadata-file sample-metadata.tsv \
    --output-dir diversity-core-metrics-phylogenetic
fi

if etapa 8; then titulo 8
  qiime diversity alpha-group-significance \
    --i-alpha-diversity diversity-core-metrics-phylogenetic/faith_pd_vector.qza \
    --m-metadata-file sample-metadata.tsv \
    --o-visualization faith-pd-group-significance.qzv
  qiime diversity alpha-group-significance \
    --i-alpha-diversity diversity-core-metrics-phylogenetic/evenness_vector.qza \
    --m-metadata-file sample-metadata.tsv \
    --o-visualization evenness-group-significance.qzv
  qiime diversity beta-group-significance \
    --i-distance-matrix diversity-core-metrics-phylogenetic/unweighted_unifrac_distance_matrix.qza \
    --m-metadata-file sample-metadata.tsv \
    --m-metadata-column body-site \
    --p-pairwise \
    --o-visualization unweighted-unifrac-body-site-group-significance.qzv
  qiime diversity beta-group-significance \
    --i-distance-matrix diversity-core-metrics-phylogenetic/unweighted_unifrac_distance_matrix.qza \
    --m-metadata-file sample-metadata.tsv \
    --m-metadata-column subject \
    --p-pairwise \
    --o-visualization unweighted-unifrac-subject-group-significance.qzv
  qiime emperor plot \
    --i-pcoa diversity-core-metrics-phylogenetic/unweighted_unifrac_pcoa_results.qza \
    --m-metadata-file sample-metadata.tsv \
    --p-custom-axes days-since-experiment-start \
    --o-visualization unweighted-unifrac-emperor-days-since-experiment-start.qzv
  qiime emperor plot \
    --i-pcoa diversity-core-metrics-phylogenetic/bray_curtis_pcoa_results.qza \
    --m-metadata-file sample-metadata.tsv \
    --p-custom-axes days-since-experiment-start \
    --o-visualization bray-curtis-emperor-days-since-experiment-start.qzv
fi

if etapa 9; then titulo 9
  qiime diversity alpha-rarefaction \
    --i-table table.qza \
    --i-phylogeny rooted-tree.qza \
    --p-max-depth 4000 \
    --m-metadata-file sample-metadata.tsv \
    --o-visualization alpha-rarefaction.qzv
fi

if etapa 10; then titulo 10
  # Classificador "suboptimal" do tutorial (Greengenes 13_8, desatualizado, so para aprender).
  wget -O 'reference-sequences.qza' "$BASE/reference-sequences.qza"
  wget -O 'reference-taxonomy.qza' "$BASE/reference-taxonomy.qza"
  qiime feature-classifier fit-classifier-naive-bayes \
    --i-reference-reads reference-sequences.qza \
    --i-reference-taxonomy reference-taxonomy.qza \
    --o-classifier suboptimal-16S-rRNA-classifier.qza
  qiime feature-classifier classify-sklearn \
    --i-classifier suboptimal-16S-rRNA-classifier.qza \
    --i-reads rep-seqs.qza \
    --o-classification taxonomy.qza
  qiime metadata tabulate \
    --m-input-file taxonomy.qza \
    --o-visualization taxonomy.qzv
  qiime taxa barplot \
    --i-table table.qza \
    --i-taxonomy taxonomy.qza \
    --m-metadata-file sample-metadata.tsv \
    --o-visualization taxa-bar-plots.qzv
fi

if etapa 11; then titulo 11
  qiime feature-table filter-samples \
    --i-table table.qza \
    --m-metadata-file sample-metadata.tsv \
    --p-where '[body-site]="gut"' \
    --o-filtered-table gut-table.qza
  qiime composition ancombc \
    --i-table gut-table.qza \
    --m-metadata-file sample-metadata.tsv \
    --p-formula subject \
    --o-differentials ancombc-subject.qza
  qiime composition da-barplot \
    --i-data ancombc-subject.qza \
    --o-visualization da-barplot-subject.qzv
  qiime taxa collapse \
    --i-table gut-table.qza \
    --i-taxonomy taxonomy.qza \
    --p-level 6 \
    --o-collapsed-table gut-table-l6.qza
  qiime composition ancombc \
    --i-table gut-table-l6.qza \
    --m-metadata-file sample-metadata.tsv \
    --p-formula subject \
    --o-differentials l6-ancombc-subject.qza
  qiime composition da-barplot \
    --i-data l6-ancombc-subject.qza \
    --o-visualization l6-da-barplot-subject.qzv
fi

echo; echo "Pronto. Resultados em: $(pwd)"
