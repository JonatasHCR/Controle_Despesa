"""Upload, previa e confirmacao da importacao."""

from __future__ import annotations

import tempfile
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.auth.guardas import requer, usuario_atual
from app.extensions import db, limiter
from app.importacao.servico import analisar, gravar

bp = Blueprint("importacao", __name__, url_prefix="/importacao")

CHAVE_ARQUIVO = "importacao_arquivo"


@bp.get("/")
@requer("operador")
def enviar():
    return render_template("importacao/enviar.html", secao="importacao")


@bp.get("/modelo")
@requer("operador")
def modelo():
    """A planilha-modelo, com as colunas esperadas e as regras."""
    from app.importacao.modelo import gerar

    return Response(
        gerar(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="modelo-importacao-despesas.xlsx"'
        },
    )


@bp.post("/previa")
@requer("operador")
@limiter.limit("10 per minute")
def previa():
    arquivo = request.files.get("planilha")
    if arquivo is None or not arquivo.filename:
        flash("Escolha uma planilha.", "erro")
        return redirect(url_for("importacao.enviar"))

    if not arquivo.filename.lower().endswith(".xlsx"):
        flash("O arquivo precisa ser .xlsx.", "erro")
        return redirect(url_for("importacao.enviar"))

    # O arquivo fica em disco entre a previa e a confirmacao: HTTP nao guarda
    # estado, e pedir o upload de novo na confirmacao seria pior.
    destino = Path(tempfile.gettempdir()) / f"import-{usuario_atual().id}.xlsx"
    arquivo.save(destino)

    try:
        resultado = analisar(db.session, destino, arquivo_nome=arquivo.filename)
    except ValueError as erro:
        destino.unlink(missing_ok=True)
        flash(str(erro), "erro")
        return redirect(url_for("importacao.enviar"))

    session[CHAVE_ARQUIVO] = {"caminho": str(destino), "nome": arquivo.filename}
    return render_template("importacao/previa.html", secao="importacao", previa=resultado)


@bp.post("/confirmar")
@requer("operador")
@limiter.limit("10 per minute")
def confirmar():
    guardado = session.pop(CHAVE_ARQUIVO, None)
    if not guardado:
        flash("A prévia expirou. Envie a planilha de novo.", "erro")
        return redirect(url_for("importacao.enviar"))

    caminho = Path(guardado["caminho"])
    if not caminho.exists():
        flash("O arquivo da prévia não está mais disponível. Envie de novo.", "erro")
        return redirect(url_for("importacao.enviar"))

    try:
        resultado = analisar(db.session, caminho, arquivo_nome=guardado["nome"])
        importacao = gravar(db.session, resultado, usuario=usuario_atual())
    except ValueError as erro:
        flash(str(erro), "erro")
        return redirect(url_for("importacao.enviar"))
    finally:
        caminho.unlink(missing_ok=True)

    current_app.logger.info(
        "importacao %s: %s criados, %s atualizados",
        importacao.id,
        importacao.criados,
        importacao.atualizados,
    )
    flash(
        f"Importação concluída: {importacao.criados} criados, "
        f"{importacao.atualizados} atualizados, "
        f"{importacao.linhas_ignoradas} totais ignorados.",
        "",
    )
    return redirect(url_for("despesas.painel"))
