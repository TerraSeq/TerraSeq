"""
Mensagens ao usuário (e-mail e comentário de Issue), validação do pedido e
aviso de erro -- compartilhados por main.py (planilha) e main_issues.py (Issues).

Todo texto enviado ao usuário é bilíngue (português e inglês) e direto.
Erros que o usuário pode corrigir (primer inválido, número fora do formato,
banco desconhecido) viram `PedidoInvalido` e voltam para ele com a lista do que
ajustar; erros internos (BLAST, servidor) avisam o usuário de forma genérica e
mandam o detalhe técnico para a equipe (EMAIL_ADMIN, por padrão o próprio
remetente).
"""
import os
import re
import smtplib
import traceback
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

NOME_EQUIPE = "TerraSeq"
IUPAC = set("ACGTRYSWKMBDHVN")


class PedidoInvalido(Exception):
    """O pedido tem problemas que o próprio usuário pode corrigir.
    `problemas` é uma lista de (texto_pt, texto_en)."""

    def __init__(self, problemas):
        super().__init__("; ".join(pt for pt, _ in problemas))
        self.problemas = list(problemas)


# --------------------------------------------------------------------------- validação
def _inteiro(valor):
    """int a partir de int/float inteiro ou string só com dígitos; senão None."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        return int(valor) if valor == int(valor) else None
    s = str(valor).strip()
    return int(s) if re.fullmatch(r"\d+", s) else None


def _decimal(valor):
    """float a partir de número ou string com PONTO decimal; senão None."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    s = str(valor).strip()
    return float(s) if re.fullmatch(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?", s) else None


def _problemas_primer(chave, nome_pt, nome_en, req):
    seq = str(req.get(chave, "")).strip().upper()
    problemas = []
    invalidos = sorted(set(seq) - IUPAC)
    if invalidos:
        lista = ", ".join(f'"{c}"' for c in invalidos)
        problemas.append((
            f"{nome_pt} inválido: caracteres não permitidos ({lista}). Use apenas A, C, G, T e os códigos IUPAC "
            f"(R, Y, S, W, K, M, B, D, H, V, N), sem espaços, números ou marcações como 5'/3'.",
            f"Invalid {nome_en}: characters not allowed ({lista}). Use only A, C, G, T and IUPAC codes "
            f"(R, Y, S, W, K, M, B, D, H, V, N), with no spaces, numbers or 5'/3' marks.",
        ))
    elif not 10 <= len(seq) <= 40:
        problemas.append((
            f"{nome_pt} com {len(seq)} nucleotídeos; o tamanho aceito é de 10 a 40.",
            f"{nome_en[0].upper() + nome_en[1:]} has {len(seq)} nucleotides; the accepted length is 10 to 40.",
        ))
    return problemas


def validar_pedido(req, bancos_validos=None):
    """Confere o pedido ANTES de rodar o BLAST. Devolve a lista de
    (texto_pt, texto_en) com o que o usuário precisa corrigir (vazia = ok).
    Campos vazios usam o padrão do pipeline e não são erro."""
    problemas = []
    problemas += _problemas_primer("Primer forward", "Primer forward", "forward primer", req)
    problemas += _problemas_primer("Primer reverse", "Primer reverse", "reverse primer", req)
    fwd = str(req.get("Primer forward", "")).strip().upper()
    rev = str(req.get("Primer reverse", "")).strip().upper()
    if fwd and fwd == rev:
        problemas.append(("Os primers forward e reverse são idênticos; confira se o reverse foi copiado corretamente.",
                          "The forward and reverse primers are identical; check that the reverse primer was copied correctly."))

    email = str(req.get("Email", "")).strip()
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        problemas.append((f'E-mail "{email}" inválido; sem um e-mail correto não conseguimos enviar o resultado.',
                          f'E-mail "{email}" is invalid; without a valid e-mail we cannot send you the result.'))

    def campo(chave, padrao):
        v = req.get(chave, padrao)
        return padrao if v is None or str(v).strip() == "" else v

    tmin = _inteiro(campo("Tamanho do amplicon: MIN", 20))
    tmax = _inteiro(campo("Tamanho do amplicon: MAX", 9999))
    if tmin is None:
        problemas.append(("Tamanho mínimo do amplicon deve ser um número inteiro (ex.: 2000).",
                          "Minimum amplicon size must be a whole number (e.g. 2000)."))
    if tmax is None:
        problemas.append(("Tamanho máximo do amplicon deve ser um número inteiro (ex.: 8000).",
                          "Maximum amplicon size must be a whole number (e.g. 8000)."))
    if tmin is not None and tmax is not None and tmin > tmax:
        problemas.append((f"Tamanho mínimo do amplicon ({tmin}) é maior que o máximo ({tmax}).",
                          f"Minimum amplicon size ({tmin}) is greater than the maximum ({tmax})."))

    mm = _inteiro(campo("Máximo de Mismatches na extremidade 3", 0))
    if mm is None or not 0 <= mm <= 5:
        problemas.append(("Máximo de mismatches deve ser um número inteiro de 0 a 5 (ex.: 3).",
                          "Maximum mismatches must be a whole number from 0 to 5 (e.g. 3)."))

    ev = _decimal(campo("E-value máximo", 10.0))
    if ev is None or ev <= 0:
        problemas.append(("E-value máximo deve ser um número maior que zero, com ponto decimal (ex.: 10 ou 0.001).",
                          "Maximum E-value must be a number greater than zero, with a decimal point (e.g. 10 or 0.001)."))

    cob = _inteiro(campo("Cobertura mínima", 0))
    if cob is None or not 0 <= cob <= 100:
        problemas.append(("Cobertura mínima deve ser um número inteiro de 0 a 100 (ex.: 70).",
                          "Minimum coverage must be a whole number from 0 to 100 (e.g. 70)."))

    tm = _decimal(campo("Temperatura de Melting mínima (Tm)", 0))
    if tm is None or tm < 0:
        problemas.append(("Temperatura de melting mínima (Tm) deve ser um número, 0 ou maior, com ponto decimal (ex.: 50.5).",
                          "Minimum melting temperature (Tm) must be a number, 0 or greater, with a decimal point (e.g. 50.5)."))

    hits = _inteiro(campo("Limite de hits", 30000))
    if hits is None or hits < 1:
        problemas.append(("Limite de hits deve ser um número inteiro maior que zero (ex.: 30000).",
                          "Hit limit must be a whole number greater than zero (e.g. 30000)."))

    if bancos_validos is not None:
        banco = str(req.get("Banco de Dados", "")).strip().lower()
        if not banco:
            opcoes = ", ".join(sorted(bancos_validos))
            problemas.append((f"Banco de dados não informado. Opções: {opcoes}.",
                              f"Database not provided. Options: {opcoes}."))
        elif banco not in bancos_validos:
            opcoes = ", ".join(sorted(bancos_validos))
            problemas.append((f'Banco de dados "{banco}" não reconhecido. Opções: {opcoes}.',
                              f'Database "{banco}" not recognized. Options: {opcoes}.'))
    return problemas


# --------------------------------------------------------------------------- textos
def montar_email_sucesso(req_id, link):
    assunto = f"[{NOME_EQUIPE}] Análise concluída / Analysis completed – {req_id}"
    corpo = (
        "Olá,\n\n"
        "Sua análise in silico foi concluída.\n\n"
        f"ID: {req_id}\n"
        f"Relatório: {link}\n\n"
        'Se o link exibir "404", aguarde 1 a 2 minutos (publicação em andamento) e atualize a página.\n\n'
        "Atenciosamente,\n"
        f"Equipe {NOME_EQUIPE}\n\n"
        "----------------------------------------\n\n"
        "Hello,\n\n"
        "Your in silico analysis is complete.\n\n"
        f"ID: {req_id}\n"
        f"Report: {link}\n\n"
        'If the link shows "404", wait 1–2 minutes (publishing in progress) and refresh the page.\n\n'
        "Kind regards,\n"
        f"{NOME_EQUIPE} Team\n"
    )
    return assunto, corpo


def _itens(problemas, idx):
    return "\n".join(f"  • {p[idx]}" for p in problemas)


def montar_email_pedido_invalido(req_id, problemas):
    assunto = f"[{NOME_EQUIPE}] Pedido não processado / Request not processed – {req_id}"
    corpo = (
        "Olá,\n\n"
        f"Não foi possível processar o pedido {req_id}. Corrija os itens abaixo e envie um novo pedido:\n\n"
        f"{_itens(problemas, 0)}\n\n"
        "Atenciosamente,\n"
        f"Equipe {NOME_EQUIPE}\n\n"
        "----------------------------------------\n\n"
        "Hello,\n\n"
        f"Request {req_id} could not be processed. Please fix the items below and submit a new request:\n\n"
        f"{_itens(problemas, 1)}\n\n"
        "Kind regards,\n"
        f"{NOME_EQUIPE} Team\n"
    )
    return assunto, corpo


def montar_email_erro_interno(req_id):
    assunto = f"[{NOME_EQUIPE}] Erro no processamento / Processing error – {req_id}"
    corpo = (
        "Olá,\n\n"
        f"Ocorreu um erro no servidor ao processar o pedido {req_id}. "
        "Não há nada a corrigir no seu pedido; a equipe foi avisada.\n\n"
        "Atenciosamente,\n"
        f"Equipe {NOME_EQUIPE}\n\n"
        "----------------------------------------\n\n"
        "Hello,\n\n"
        f"A server error occurred while processing request {req_id}. "
        "Nothing needs to be changed in your request; the team has been notified.\n\n"
        "Kind regards,\n"
        f"{NOME_EQUIPE} Team\n"
    )
    return assunto, corpo


def comentario_sucesso(numero_analise, link):
    return (
        f"✅ **Análise #{numero_analise} concluída / Analysis #{numero_analise} completed**\n\n"
        f"👉 **[Abrir relatório / Open report]({link})**\n\n"
        'Se aparecer "404", aguarde 1 a 2 minutos e atualize a página (`Ctrl + F5`).\n'
        'If you see "404", wait 1–2 minutes and refresh the page (`Ctrl + F5`).'
    )


def comentario_pedido_invalido(numero_analise, problemas):
    pt = "\n".join(f"- {p[0]}" for p in problemas)
    en = "\n".join(f"- {p[1]}" for p in problemas)
    return (
        f"❌ **Análise #{numero_analise} não processada / Analysis #{numero_analise} not processed**\n\n"
        f"Corrija os itens abaixo e abra uma nova Issue:\n{pt}\n\n---\n\n"
        f"Please fix the items below and open a new Issue:\n{en}"
    )


def comentario_erro_interno(numero_analise):
    return (
        f"❌ **Erro no processamento da análise #{numero_analise} / Processing error on analysis #{numero_analise}**\n\n"
        "Ocorreu um erro no servidor. Não há nada a corrigir no seu pedido; a equipe foi avisada.\n\n"
        "A server error occurred. Nothing needs to be changed in your request; the team has been notified."
    )


# --------------------------------------------------------------------------- envio
def enviar_email(destino, assunto, corpo):
    """Envia um e-mail de texto. Devolve True/False; nunca levanta exceção."""
    if not destino or "@" not in destino:
        print(f"   ⏩ E-mail ignorado: destinatário ausente ou inválido ({destino!r}).")
        return False
    remetente = os.environ.get("EMAIL_REMETENTE", "")
    msg = MIMEMultipart()
    msg["From"] = remetente
    msg["To"] = destino
    msg["Subject"] = assunto
    msg.attach(MIMEText(corpo, "plain", "utf-8"))
    try:
        server = smtplib.SMTP(os.environ.get("SMTP_SERVER", "smtp.gmail.com"),
                              int(os.environ.get("SMTP_PORT", "587")), timeout=10)
        server.starttls()
        server.login(remetente, os.environ.get("EMAIL_SENHA", ""))
        server.sendmail(remetente, destino, msg.as_string())
        server.quit()
        print(f"   ✅ E-mail enviado com sucesso para: {destino}")
        return True
    except Exception as e:
        print(f"   ⚠️ Erro ao enviar e-mail: {e}")
        return False


def enviar_email_sucesso(destino, req_id, link):
    print("📧 Preparando disparo de e-mail...")
    assunto, corpo = montar_email_sucesso(req_id, link)
    return enviar_email(destino, assunto, corpo)


def resumo_do_erro(erro):
    """Texto curto (uma linha) para registrar na planilha."""
    if isinstance(erro, PedidoInvalido):
        return "; ".join(pt for pt, _ in erro.problemas)[:300]
    return f"erro interno: {type(erro).__name__}: {erro}"[:300]


def notificar_falha(email_usuario, req_id, erro, req=None, origem=""):
    """Avisa o usuário (pedido inválido -> o que corrigir; erro interno -> aviso
    genérico) e, em erro interno, manda o detalhe técnico para a equipe."""
    if isinstance(erro, PedidoInvalido):
        assunto, corpo = montar_email_pedido_invalido(req_id, erro.problemas)
        enviar_email(email_usuario, assunto, corpo)
        return
    assunto, corpo = montar_email_erro_interno(req_id)
    enviar_email(email_usuario, assunto, corpo)

    admin = os.environ.get("EMAIL_ADMIN") or os.environ.get("EMAIL_REMETENTE", "")
    detalhe = "".join(traceback.format_exception(type(erro), erro, erro.__traceback__))
    for atributo in ("stderr", "stdout"):
        saida = getattr(erro, atributo, None)
        if saida:
            detalhe += f"\n--- {atributo} ---\n{saida}"
    pedido = "\n".join(f"  {k}: {v}" for k, v in (req or {}).items() if k != "Email")
    enviar_email(
        admin,
        f"[{NOME_EQUIPE}] ERRO no pipeline ({origem}) – {req_id}",
        f"Falha ao processar {req_id} (origem: {origem}).\nUsuário: {email_usuario or '(sem e-mail)'}\n\n"
        f"Pedido:\n{pedido}\n\n{detalhe}",
    )
