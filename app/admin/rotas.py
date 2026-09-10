"""Painel administrativo. Todas as rotas exigem perfil admin."""

from __future__ import annotations

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from sqlalchemy import select

from app.admin import manutencao
from app.auditoria.servico import registrar
from app.auth.guardas import requer, usuario_atual
from app.despesas.consulta import filtro_da_query, opcoes
from app.extensions import db, limiter
from app.models import PERFIS, Usuario

bp = Blueprint("admin", __name__, url_prefix="/administracao")


@bp.get("/")
@requer("admin")
def painel():
    return render_template(
        "admin/painel.html",
        secao="admin",
        backups=manutencao.listar_backups(),
        alvos=manutencao.ALVOS,
        opcoes=opcoes(db.session),
        filtro=filtro_da_query(request.args, sessao=db.session),
        pessoas=db.session.scalars(select(Usuario).order_by(Usuario.nome)).all(),
        perfis=PERFIS,
    )


@bp.post("/backups")
@requer("admin")
@limiter.limit("6 per minute")
def criar_backup():
    try:
        arquivo = manutencao.gerar_backup()
    except manutencao.ErroDeManutencao as erro:
        flash(str(erro), "erro")
        return redirect(url_for("admin.painel"))

    registrar(
        db.session,
        acao="manutencao.backup",
        usuario=usuario_atual(),
        alvo_tipo="backup",
        payload={"arquivo": arquivo.name, "bytes": arquivo.stat().st_size},
    )
    db.session.commit()
    flash(f"Backup gerado: {arquivo.name}", "")
    return redirect(url_for("admin.painel"))


@bp.get("/backups/<nome>")
@requer("admin")
def baixar_backup(nome: str):
    try:
        arquivo = manutencao.resolver_arquivo(nome)
    except manutencao.ErroDeManutencao as erro:
        flash(str(erro), "erro")
        return redirect(url_for("admin.painel"))
    return send_file(arquivo, as_attachment=True, download_name=arquivo.name)


@bp.post("/contagem")
@requer("admin")
def contagem():
    """Dry-run: quantos registros a limpeza pegaria com o filtro atual."""
    alvo = request.form.get("alvo", "")
    filtro = filtro_da_query(request.form, sessao=db.session)
    try:
        quantidade = manutencao.contar(db.session, alvo, filtro)
    except manutencao.ErroDeManutencao as erro:
        # Template, e nao f-string: `alvo` vem do formulario e voltava cru para
        # o HTML. A CSP fechada impedia a execucao, mas a defesa nao pode
        # depender so dela.
        return render_template("admin/_erro.html", mensagem=str(erro)), 400
    return render_template("admin/_contagem.html", quantidade=quantidade, alvo=alvo)


@bp.post("/limpeza")
@requer("admin")
@limiter.limit("6 per minute")
def limpeza():
    if request.form.get("confirmacao") != manutencao.PALAVRA_LIMPAR:
        flash(f'Digite "{manutencao.PALAVRA_LIMPAR}" para confirmar a limpeza.', "erro")
        return redirect(url_for("admin.painel"))

    alvo = request.form.get("alvo", "")
    filtro = filtro_da_query(request.form, sessao=db.session)
    try:
        quantidade = manutencao.limpar(db.session, alvo, filtro)
    except manutencao.ErroDeManutencao as erro:
        db.session.rollback()
        flash(str(erro), "erro")
        return redirect(url_for("admin.painel"))

    registrar(
        db.session,
        acao="manutencao.limpeza",
        usuario=usuario_atual(),
        alvo_tipo="limpeza",
        payload={"alvo": alvo, "removidos": quantidade},
    )
    db.session.commit()
    flash(f"{quantidade} registro(s) removido(s) de {alvo}.", "")
    return redirect(url_for("admin.painel"))


@bp.post("/restauracao")
@requer("admin")
@limiter.limit("3 per minute")
def restauracao():
    if request.form.get("confirmacao") != manutencao.PALAVRA_RESTAURAR:
        flash(f'Digite "{manutencao.PALAVRA_RESTAURAR}" para confirmar a restauração.', "erro")
        return redirect(url_for("admin.painel"))

    nome = request.form.get("arquivo", "")
    usuario = usuario_atual()
    try:
        restaurado = manutencao.restaurar(db.session, nome)
    except manutencao.ErroDeManutencao as erro:
        flash(str(erro), "erro")
        return redirect(url_for("admin.painel"))

    # O registro vai depois, na conexao nova: o banco de agora e o do backup.
    registrar(
        db.session,
        acao="manutencao.restauracao",
        usuario=usuario,
        alvo_tipo="backup",
        payload={"arquivo": restaurado},
    )
    db.session.commit()
    flash(f"Banco restaurado a partir de {restaurado}.", "")
    return redirect(url_for("admin.painel"))


@bp.post("/pessoas/<int:identificador>/perfil")
@requer("admin")
def mudar_perfil(identificador: int):
    perfil = request.form.get("perfil", "")
    if perfil not in PERFIS:
        flash("Perfil desconhecido.", "erro")
        return redirect(url_for("admin.painel"))

    pessoa = db.session.get(Usuario, identificador)
    if pessoa is None:
        flash("Usuário não encontrado.", "erro")
        return redirect(url_for("admin.painel"))

    if pessoa.id == usuario_atual().id and perfil != "admin":
        flash("Você não pode rebaixar a si mesmo.", "erro")
        return redirect(url_for("admin.painel"))

    anterior, pessoa.perfil = pessoa.perfil, perfil
    registrar(
        db.session,
        acao="usuario.perfil",
        usuario=usuario_atual(),
        alvo_tipo="usuario",
        alvo_id=pessoa.id,
        payload={"email": pessoa.email, "de": anterior, "para": perfil},
    )
    db.session.commit()
    flash(f"{pessoa.nome} agora é {perfil}.", "")
    return redirect(url_for("admin.painel"))
