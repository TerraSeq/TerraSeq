"""
Depois que a análise termina (pipeline.run_pipeline): pôr na vitrine, publicar
no GitHub Pages e avisar o pesquisador por e-mail. Usado pelos dois monitores.

Os monitores chamam, dentro da trava "publicacao" (bloqueios.py):

    publicacao.atualizar_vitrine_html(req, req_id, resultado_json)
    publicacao.publicar_no_github(req_id)

e depois, fora da trava:

    publicacao.enviar_email_notificacao(email, req_id)
"""
import os
import subprocess

import configuracao
import notificacoes
import vitrine

RAIZ_PROJETO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def atualizar_vitrine_html(req, req_id, resultado_json=None):
    """Põe a análise na vitrine do site (docs/dados/vitrine.json).

    O nome ficou da época em que a vitrine era escrita direto no HTML; hoje só
    repassa para vitrine.adicionar_analise. Um erro aqui não derruba o monitor:
    o relatório já existe e continua sendo publicado.
    """
    try:
        vitrine.adicionar_analise(req, req_id, resultado_json)
    except Exception as e:
        print(f"   ⚠️ Erro ao atualizar vitrine: {e}")


def publicar_no_github(req_id):
    """git add/commit/push da vitrine e da pasta do relatório.

    Se o push for rejeitado porque o GitHub avançou (outra pessoa, ou o Claude,
    publicou algo no main), faz um pull e tenta de novo, em vez de deixar o
    relatório preso no servidor.
    """
    print("🚀 Iniciando publicação no GitHub Pages...")

    try:
        # Só a lista da vitrine e a pasta DESTE relatório: um "git add docs/" levaria
        # junto a pasta pela metade de outra análise que está rodando ao mesmo tempo.
        subprocess.run(["git", "add", vitrine.CAMINHO_VITRINE_GIT, f"docs/reports/{req_id}"], cwd=RAIZ_PROJETO, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "commit", "-m", f"Report {req_id}"], cwd=RAIZ_PROJETO, check=True, stdout=subprocess.DEVNULL)
    except subprocess.CalledProcessError as e:
        print(f"   ⚠️ Erro ao commitar as mudanças: {e}")
        return

    try:
        subprocess.run(["git", "push"], cwd=RAIZ_PROJETO, check=True, capture_output=True, text=True)
        print("   🌐 Relatório pushado com sucesso!")
        return
    except subprocess.CalledProcessError:
        print("   ⚠️ Push rejeitado (remoto avançou). Tentando sincronizar automaticamente...")

    try:
        subprocess.run(["git", "pull", "--no-edit"], cwd=RAIZ_PROJETO, check=True, capture_output=True, text=True)
        subprocess.run(["git", "push"], cwd=RAIZ_PROJETO, check=True, capture_output=True, text=True)
        print("   🌐 Sincronizado com o GitHub e relatório pushado com sucesso!")
    except subprocess.CalledProcessError as e:
        print(f"   🔥 Falha ao sincronizar automaticamente com o GitHub (exit code {e.returncode}):")
        print(e.stdout or "")
        print(e.stderr or "")
        print("   ⚠️ O relatório está salvo localmente (commitado), mas precisa de um 'git pull'/merge manual para ir ao ar.")


def enviar_email_notificacao(email_destino, req_id):
    """E-mail de "relatório pronto", com o link público do relatório."""
    notificacoes.enviar_email_sucesso(email_destino, req_id, configuracao.link_relatorio(req_id))
