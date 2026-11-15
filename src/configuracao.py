"""
Configuração comum dos dois monitores (main.py e main_issues.py).

    import configuracao
    configuracao.iniciar()          # uma vez, no começo do monitor

iniciar():
  - eleva o limite de arquivos abertos do processo (o BLAST precisa);
  - carrega o .env (que NÃO vai pro Git; modelo em .env.example);
  - confere as variáveis obrigatórias e para com uma mensagem clara se faltar alguma;
  - configura o e-mail do NCBI (Entrez).

Depois disso, repositorio() e link_relatorio(req_id) dão o repositório do
site e o endereço público de um relatório.
"""
import os
import resource
import sys

from Bio import Entrez
from dotenv import load_dotenv

# Variáveis que todo monitor precisa (o main_issues.py também exige GITHUB_TOKEN).
VARIAVEIS_OBRIGATORIAS = ["ENTREZ_EMAIL", "EMAIL_REMETENTE", "EMAIL_SENHA"]

# Repositório do site, quando o .env não diz (GITHUB_REPO_OWNER / GITHUB_REPO_NAME).
REPOSITORIO_PADRAO = ("TerraSeq", "TerraSeq")


def elevar_limite_arquivos(alvo=65536):
    """Eleva o limite de arquivos abertos do processo (ulimit -n).

    O banco "eucariotos" combina dezenas de bancos BLAST numa busca só, e os
    maiores (bacteria, ascomycota, sar...) são divididos em vários volumes --
    a soma de arquivos que o blastn precisa abrir ao mesmo tempo passou do
    padrão do Linux (1024) depois que os grupos novos foram indexados,
    causando "BLAST Database error: Cannot memory map ... Number of files
    opened: 1020". Isso sobe o limite do processo (não precisa de sudo nem
    mexer no shell), até o teto que o sistema permitir.
    """
    try:
        limite_atual, limite_maximo = resource.getrlimit(resource.RLIMIT_NOFILE)
        novo_limite = alvo if limite_maximo == resource.RLIM_INFINITY else min(alvo, limite_maximo)
        if limite_atual < novo_limite:
            resource.setrlimit(resource.RLIMIT_NOFILE, (novo_limite, limite_maximo))
            print(f"🔧 Limite de arquivos abertos elevado de {limite_atual} para {novo_limite}.")
    except (ValueError, OSError) as e:
        print(f"⚠️ Não foi possível elevar o limite de arquivos abertos automaticamente ({e}).")
        print("   Se o erro 'Cannot memory map ... .nhr' persistir, rode antes: ulimit -n 65536")


def obter_env_obrigatoria(nome):
    """Valor da variável de ambiente; se faltar, explica e encerra o programa."""
    valor = os.environ.get(nome)
    if not valor:
        print(f"❌ Erro fatal: variável de ambiente '{nome}' não encontrada.")
        print("   Verifique se o arquivo .env existe na raiz do projeto e está preenchido.")
        print("   Use .env.example como modelo.")
        sys.exit(1)
    return valor


def iniciar():
    elevar_limite_arquivos()
    load_dotenv()
    for nome in VARIAVEIS_OBRIGATORIAS:
        obter_env_obrigatoria(nome)
    Entrez.email = os.environ["ENTREZ_EMAIL"]


def repositorio():
    """(dono, nome) do repositório do site no GitHub."""
    return (os.environ.get("GITHUB_REPO_OWNER", REPOSITORIO_PADRAO[0]),
            os.environ.get("GITHUB_REPO_NAME", REPOSITORIO_PADRAO[1]))


def link_relatorio(req_id):
    """Endereço público do relatório no GitHub Pages."""
    dono, nome = repositorio()
    return f"https://{dono}.github.io/{nome}/reports/{req_id}/"
