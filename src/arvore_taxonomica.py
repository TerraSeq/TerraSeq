"""
Monta as árvores do relatório a partir dos hits do BLAST:

  - a árvore taxonômica (domínio > ... > espécie, com a contagem de hits em cada nó);
  - a classificação funcional (função ecológica > grande grupo > espécies), via ecologia.py;
  - os metadados de cada espécie (accession, descrição, tamanho, amplicons).

A linhagem de cada sequência vem primeiro da base local (taxonomia_local.py,
sem rede); só se a sequência não estiver mapeada localmente é que consulta o
NCBI (Entrez), mais lento e com limite de taxa.

Uso (run_pipeline em main.py / main_issues.py):

    from arvore_taxonomica import construir_arvore_aninhada
    arvore, metadados, papeis_funcionais = construir_arvore_aninhada(ids, total_matches, hits_por_id)
"""
import time

from Bio import Entrez

import taxonomia_local
from ecologia import FUNCOES_ECOLOGICAS, NAO_CLASSIFICADO, classificar_ecologia

# Prefixos de ID do BLAST no formato "gb|JBAMJC010000001.1|": o accession é o 2º campo.
PREFIXOS_DE_ID = ["gb", "ref", "emb", "dbj", "gi"]


def accession_do_id(subject_id):
    """'gb|JBAMJC010000001.1|' -> 'JBAMJC010000001'; 'NC_000913.3' -> 'NC_000913'.

    Pega o campo certo quando o ID tem prefixo (senão pegaria "gb" como se
    fosse o accession) e tira a versão (".1")."""
    partes = subject_id.split('|')
    acc = partes[1] if len(partes) > 1 and partes[0].lower() in PREFIXOS_DE_ID else partes[0]
    return acc.split('.')[0]


def descobrir_rank(taxa, profundidade, tamanho_total):
    """Nível taxonômico aproximado de um nome da linhagem, pelo próprio nome
    (sufixos clássicos: -mycota, -ales, -aceae...) e pela posição na linhagem."""
    t = taxa.lower()
    if t in ["bacteria", "archaea", "eukaryota", "viruses"]: return "domain"
    if t in ["fungi", "metazoa", "viridiplantae"]: return "kingdom"
    if t.endswith("ota") or t.endswith("mycota") or t.endswith("phyta"): return "phylum"
    if (t.endswith("ia") and profundidade < 6) or t.endswith("mycetes") or t.endswith("opsida") or t.endswith("phyceae"): return "class"
    if t.endswith("ales"): return "order"
    if t.endswith("aceae") or t.endswith("idae"): return "family"
    if profundidade == tamanho_total - 1: return "species"
    if profundidade == tamanho_total - 2: return "genus"
    return "clade"


def construir_arvore_aninhada(lista_ids, total_matches, hits_data_map):
    """lista_ids: IDs únicos das sequências com hit (subject_id do BLAST).
    total_matches: total de hits da análise (raiz da árvore).
    hits_data_map: {subject_id: [hit, ...]} -- os amplicons de cada sequência.

    Devolve (arvore_taxonomica, metadados_por_especie, papeis_funcionais)."""
    total_organismos = len(lista_ids)
    print(f"🌳 Consultando NCBI para {total_organismos} organismos únicos...")
    paths = []
    meta_dict = {}

    # Classificação funcional (Atlas, Cap. 4, p.112): começa com todas as
    # funções de ecologia.py, inclusive "Fora do Escopo Principal" e
    # "Função Indefinida", mesmo que alguma fique vazia.
    functional_roles = {funcao: {} for funcao in FUNCOES_ECOLOGICAS}

    for index, subject_id in enumerate(lista_ids, 1):
        print(f"   ⏳ Classificando [{index}/{total_organismos}]: {subject_id}...", end="\r")
        try:
            acc = accession_do_id(subject_id)

            # 1ª tentativa: manifesto local (accession -> taxId), gerado por
            # scripts_auxiliares/gerar_manifesto_taxid.py -- não consulta o
            # NCBI pela rede, é instantâneo. Só cai pro Entrez (mais lento,
            # com limite de taxa) se a sequência não estiver mapeada
            # localmente (ex: banco novo, ainda sem manifesto gerado).
            taxid = taxonomia_local.taxid_por_accession(acc)
            if taxid:
                linhagem = taxonomia_local.linhagem_por_taxid(taxid)
                if not linhagem:
                    raise ValueError("taxId sem linhagem na base de taxonomia local")
                if linhagem[0].lower() == "cellular organisms":
                    linhagem.pop(0)
                especie = linhagem[-1]
                acc_final = acc
                desc_local, tamanho_local = taxonomia_local.descricao_e_tamanho_por_accession(acc)
                desc_final = desc_local or "Descrição indisponível"
                length_final = tamanho_local if tamanho_local is not None else "N/A"
            else:
                handle = Entrez.efetch(db="nucleotide", id=acc, retmode="xml")
                records = Entrez.read(handle)
                handle.close()
                if not records:
                    raise ValueError("Sequência não encontrada no NCBI")
                rec = records[0]
                linhagem = rec["GBSeq_taxonomy"].split("; ")
                especie = rec["GBSeq_organism"]
                linhagem.append(especie)
                if linhagem[0].lower() == "cellular organisms":
                    linhagem.pop(0)
                acc_final = rec.get("GBSeq_primary-accession", acc)
                desc_final = rec.get("GBSeq_definition", "Descrição indisponível")
                length_final = rec.get("GBSeq_length", "N/A")
                time.sleep(0.4)  # só precisa respeitar o limite de taxa do NCBI no fallback

            # Peso = quantidade REAL de hits desse accession (pode ser >1 --
            # ex: gene ribossomal multi-cópia com várias cópias no mesmo
            # scaffold, cada uma gerando um hit/produto separado). "paths"
            # tem 1 entrada por accession ÚNICA (pra não reclassificar a
            # mesma sequência várias vezes, caro), mas a árvore precisa
            # contar cada hit -- daí o peso, aplicado só na hora de montar
            # a árvore mais abaixo. Sem isso, "Qtd. Matches" da árvore
            # taxonômica ficava menor que a quantidade real de produtos
            # (visível clicando na espécie), porque contava só 1 por
            # accession visitada, não por hit.
            peso = len(hits_data_map.get(subject_id, [])) or 1
            paths.append((linhagem, peso))

            if especie not in meta_dict:
                meta_dict[especie] = {
                    "info": {
                        "acc": acc_final,
                        "desc": desc_final,
                        "length": length_final
                    },
                    "amplicons": []
                }

            # Classificação funcional: cada grande grupo guarda o tamanho
            # biológico e a lista de espécies (uma entrada por sequência).
            grupo, tamanho, funcao = classificar_ecologia(linhagem)

            if grupo not in functional_roles[funcao]:
                functional_roles[funcao][grupo] = {"tamanho": tamanho, "especies": []}

            functional_roles[funcao][grupo]["especies"].append({
                "especie": especie,
                "id": acc,
                "matches": len(hits_data_map.get(subject_id, []))
            })

            if subject_id in hits_data_map:
                meta_dict[especie]["amplicons"].extend(hits_data_map[subject_id])

        except Exception:
            # Sequência que não deu pra classificar (nem local nem via NCBI):
            # vira um ramo "Unclassified" > accession, clicável como qualquer
            # outro domínio (antes era um nó "Unclassified" sem filhos, que não
            # mostrava QUAL genoma falhou).
            acc_desconhecido = accession_do_id(subject_id)

            peso_desconhecido = len(hits_data_map.get(subject_id, [])) or 1
            paths.append((["Unclassified", acc_desconhecido], peso_desconhecido))

            if acc_desconhecido not in meta_dict:
                meta_dict[acc_desconhecido] = {
                    "info": {
                        "acc": acc_desconhecido,
                        "desc": "Organismo não classificado — falha na resolução taxonômica (local e via NCBI).",
                        "length": "N/A"
                    },
                    "amplicons": []
                }
            if subject_id in hits_data_map:
                meta_dict[acc_desconhecido]["amplicons"].extend(hits_data_map[subject_id])

            grupo_nc, tamanho_nc, funcao_nc = NAO_CLASSIFICADO
            if grupo_nc not in functional_roles[funcao_nc]:
                functional_roles[funcao_nc][grupo_nc] = {"tamanho": tamanho_nc, "especies": []}
            functional_roles[funcao_nc][grupo_nc]["especies"].append({
                "especie": acc_desconhecido,
                "id": acc_desconhecido,
                "matches": len(hits_data_map.get(subject_id, []))
            })

    print(f"\n   ✅ Árvore construída com sucesso para {total_organismos} organismos!")

    # Monta a árvore aninhada a partir das linhagens, somando o peso (hits) em cada nó.
    root = {"name": "Root", "rank": "root", "matches": total_matches, "coverage": 1.0, "children": []}
    for path, peso in paths:
        current_node = root
        tamanho_path = len(path)
        for depth, taxa in enumerate(path):
            rank_correto = descobrir_rank(taxa, depth, tamanho_path)
            found_child = None
            for child in current_node["children"]:
                if child["name"] == taxa: found_child = child; break
            if found_child:
                found_child["matches"] += peso
                current_node = found_child
            else:
                new_node = {"name": taxa, "rank": rank_correto, "matches": peso, "coverage": 0.0, "children": []}
                current_node["children"].append(new_node)
                current_node = new_node

    def calc_coverage(node):
        node["coverage"] = round(node["matches"] / total_matches, 4) if total_matches > 0 else 0.0
        for child in node["children"]: calc_coverage(child)
    calc_coverage(root)

    return root, meta_dict, functional_roles
