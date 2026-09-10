"""Leitura da trilha de auditoria. Somente admin."""

from __future__ import annotations

from flask import Blueprint, render_template, request
from sqlalchemy import select

from app.auth.guardas import requer
from app.extensions import db
from app.models import Auditoria, Usuario

bp = Blueprint("auditoria", __name__, url_prefix="/auditoria")

POR_PAGINA = 60


@bp.get("/")
@requer("admin")
def lista():
    consulta = select(Auditoria).order_by(Auditoria.criado_em.desc(), Auditoria.id.desc())

    acao = (request.args.get("acao") or "").strip()
    alvo_tipo = (request.args.get("alvo_tipo") or "").strip()
    usuario_id = request.args.get("usuario", type=int)

    if acao:
        consulta = consulta.where(Auditoria.acao == acao)
    if alvo_tipo:
        consulta = consulta.where(Auditoria.alvo_tipo == alvo_tipo)
    if usuario_id:
        consulta = consulta.where(Auditoria.usuario_id == usuario_id)

    pagina = db.paginate(
        consulta,
        page=request.args.get("pagina", 1, type=int),
        per_page=POR_PAGINA,
        error_out=False,
    )

    return render_template(
        "auditoria/lista.html",
        secao="auditoria",
        pagina=pagina,
        acoes=db.session.scalars(select(Auditoria.acao).distinct().order_by(Auditoria.acao)).all(),
        tipos=db.session.scalars(
            select(Auditoria.alvo_tipo).distinct().order_by(Auditoria.alvo_tipo)
        ).all(),
        pessoas={
            usuario.id: usuario.nome for usuario in db.session.scalars(select(Usuario))
        },
        filtro_acao=acao,
        filtro_tipo=alvo_tipo,
        filtro_usuario=usuario_id,
        query_base={
            chave: valor
            for chave, valor in request.args.items()
            if chave != "pagina" and valor
        },
    )
