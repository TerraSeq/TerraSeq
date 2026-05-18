#!/usr/bin/env python
import pandas as pd
import os

def _encode_fasta_header(assay_num, target, type_str):
    if "Forward" in type_str:
        dir = "fwd"
    else:
        dir = "rev"
    return F"{assay_num}|{target}|{dir}"

def _decode_fasta_header(header_str, line_num=0):
    """
    Decodifica cabeçalho FASTA do primer.
    Aceita formatos flexíveis, desde que contenha 'fwd' ou 'rev' como última parte.
    Exemplos aceitos:
    - Primer|V4_Balzano_F|fwd
    - Ensaio1|18S|fwd
    - qualquer_coisa|fwd
    - >Primer|D11_3143R|rev
    """
    # Remove o '>' se existir e espaços extras
    header_str = header_str.strip().lstrip('>')
    
    # Divide por '|'
    spl = header_str.split("|")
    
    # Verifica se a última parte é fwd ou rev (ignorando maiúsculas/minúsculas e espaços)
    if len(spl) == 0:
        if line_num > 0:
            raise ValueError(f"Header on line {line_num} is empty.")
        else:
            raise ValueError("Header is empty.")
    
    last_part = spl[-1].strip().lower()
    
    if last_part not in ("fwd", "rev"):
        # Tenta encontrar fwd ou rev em qualquer parte
        found = False
        for part in spl:
            if part.strip().lower() in ("fwd", "rev"):
                last_part = part.strip().lower()
                found = True
                break
        if not found:
            if line_num > 0:
                raise ValueError(f"Header on line {line_num}: '{header_str}' must contain 'fwd' or 'rev'.")
            else:
                raise ValueError(f"Header: '{header_str}' must contain 'fwd' or 'rev'.")
    
    direction = last_part
    
    # O assay_number pode ser tudo antes da direção, ou tudo se não conseguirmos identificar
    if direction in header_str.lower():
        # Encontra a posição da direção
        assay_number = header_str.lower().replace(f"|{direction}", "").replace(direction, "").strip('|')
    else:
        assay_number = "|".join(spl[:-1]) if len(spl) > 1 else "Primer"
    
    if not assay_number:
        assay_number = "Primer"
    
    # Para compatibilidade com o resto do código
    return {
        "assay_number": assay_number,
        "target": assay_number,  # Usa o mesmo para simplificar
        "direction": direction
    }

def _check_and_read_valid_FASTA(file, primers=False):
    if primers:
        primer_dict = {}
    with open(file, "r") as ifile:
        lines = ifile.readlines()
        headers, seq_count, seq = 0, 0, ""
        header_completo_atual = ""
        for i in lines:
            if i[0] == ">":
                if seq != "":
                    if primers:
                        # Cria chave simplificada
                        parts = header_completo_atual.split("|")
                        if len(parts) >= 2:
                            assay_name = parts[0]
                            direction = parts[-1].lower()
                            chave_simplificada = f"{assay_name}|{direction}"
                        else:
                            chave_simplificada = header_completo_atual
                        primer_dict[chave_simplificada] = seq
                    seq_count += 1
                if primers:
                    header_completo_atual = i[1:].strip()
                    decoded = _decode_fasta_header(i, line_num=headers+1)
                headers += 1
                seq = ""
            else:
                seq += i.strip()
        if seq != "":
            if primers:
                # Cria chave simplificada para a última sequência
                parts = header_completo_atual.split("|")
                if len(parts) >= 2:
                    assay_name = parts[0]
                    direction = parts[-1].lower()
                    chave_simplificada = f"{assay_name}|{direction}"
                else:
                    chave_simplificada = header_completo_atual
                primer_dict[chave_simplificada] = seq
            seq_count += 1
    if headers == seq_count and headers > 0 and not primers:
        return True
    elif headers == seq_count and headers > 0 and primers:
        return True, primer_dict
    elif primers:
        return False, primer_dict
    else:
        return False

def _determine_primerfile_type(file):
    try:
        df = pd.read_excel(file, sheet_name=0)
        return "EXCEL"
    except ValueError:
        qual, _ = _check_and_read_valid_FASTA(file, primers=True)
        if qual:
            return "FASTA"
        else:
            return None

def _idt_to_fasta(file):
    '''
    Coverts to the output of IDT Primer Quest export to a BLASTable FASTA.

    file: file object of inputted primer file
    '''
    idt_df = pd.read_excel(file, sheet_name=0) # read first sheet in file
    expected_cols = "Type", "AssaySet", "Sequence"
    if len([x for x in expected_cols if x in idt_df.columns]) < len(expected_cols):
        raise ValueError(F"Please verify that the primers file: {file} is formatted as expected from IDT PrimerQuest.\nSee test file at https://github.com/liberjul/primer_blast_local/blob/main/test/IDT_PrimerQuest_Export.xls")
    buffer = ""
    primer_dict = {}
    for i in range(len(idt_df)):
        type_str = idt_df.Type[i] # fwd, rev, or product
        if type_str != "Product": # if a primer
            assay_num, target = idt_df.AssaySet[i].strip(")").split(" (") # get assay set and target name
            header = _encode_fasta_header(assay_num, target, type_str).replace(" ", "_")
            buffer += F">{header}\n{idt_df.Sequence[i]}\n"
            primer_dict[header] = idt_df.Sequence[i]
    return buffer.strip(), primer_dict
