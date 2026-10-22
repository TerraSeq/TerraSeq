"""
Travas entre processos (main.py e main_issues.py rodam ao mesmo tempo, cada um
processando uma análise por vez; com vários usuários, as duas pontas podem
estar ocupadas juntas).

Usam fcntl.flock em arquivos de data/locks/: o próprio sistema operacional
libera a trava se o processo morrer (nenhum arquivo "preso").

  - "publicacao": só um processo por vez atualiza a vitrine (docs/index.html) e
    faz commit/push -- evita index.lock do git, linha perdida na vitrine e um
    `git pull` com arquivo sujo.
  - "blast-pesado": só uma busca em banco grande por vez, em todo o servidor
    (o BLAST do "eucariotos" chega a 58-114GB de RAM; duas ao mesmo tempo
    estouram a memória e o Linux mata uma). Bancos pequenos não esperam.
"""
import contextlib
import fcntl
import os
import time

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DIR_LOCKS = os.path.join(RAIZ, "data", "locks")

# Bancos com este número de genomas (ou mais) entram na fila de "blast-pesado".
# Ex: eucariotos (8.369), refseqsoil, bacteria, fungi, ascomycota, basidiomycota.
LIMITE_BANCO_PESADO = 1000


@contextlib.contextmanager
def bloqueio(nome, aviso=None, intervalo=5):
    """Espera (bloqueando) até conseguir a trava `nome`; solta ao sair."""
    os.makedirs(DIR_LOCKS, exist_ok=True)
    with open(os.path.join(DIR_LOCKS, f"{nome}.lock"), "w") as arquivo:
        avisou = False
        while True:
            try:
                fcntl.flock(arquivo, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if aviso and not avisou:
                    print(aviso)
                    avisou = True
                time.sleep(intervalo)
        try:
            yield
        finally:
            fcntl.flock(arquivo, fcntl.LOCK_UN)


def bloqueio_se(condicao, nome, aviso=None):
    """Como `bloqueio`, mas sem fazer nada quando `condicao` é falsa."""
    return bloqueio(nome, aviso) if condicao else contextlib.nullcontext()
