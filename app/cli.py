"""Comandos de linha: promover usuario e importar planilha sem passar pela tela.

O perfil nunca e concedido pela interface — e a mesma escolha do radar, e a
razao e que a tela de administracao existe para operar o sistema, nao para
distribuir poder sobre ele.
"""

from __future__ import annotations

from pathlib import Path

import click
from flask import Blueprint
from sqlalchemy import func, select

from app.extensions import db
from app.models import PERFIS, Despesa, Usuario

bp = Blueprint("cli", __name__, cli_group=None)


@bp.cli.command("promover")
@click.argument("email")
@click.argument("perfil", type=click.Choice(PERFIS))
def promover(email: str, perfil: str) -> None:
    """Muda o perfil de alguem: flask promover fulano@x.com admin"""
    usuario = db.session.scalars(
        select(Usuario).where(func.lower(Usuario.email) == email.lower())
    ).first()
    if usuario is None:
        raise click.ClickException(
            f"{email} nao existe. A pessoa precisa entrar uma vez para ser criada."
        )

    anterior, usuario.perfil = usuario.perfil, perfil
    db.session.commit()
    click.echo(f"{usuario.nome}: {anterior} -> {perfil}")


@bp.cli.command("usuarios")
def usuarios() -> None:
    """Lista quem ja entrou no sistema."""
    pessoas = db.session.scalars(select(Usuario).order_by(Usuario.nome)).all()
    if not pessoas:
        click.echo("ninguem entrou ainda")
        return
    for pessoa in pessoas:
        marca = "" if pessoa.ativo else "  (sem o grupo)"
        click.echo(f"{pessoa.perfil:9} {pessoa.email:40} {pessoa.nome}{marca}")


@bp.cli.command("importar")
@click.argument("caminho", type=click.Path(exists=True, dir_okay=False))
@click.option("--email", help="quem fica registrado como autor da importacao")
@click.option("--previa", is_flag=True, help="so mostra o resumo, sem gravar")
def importar(caminho: str, email: str | None, previa: bool) -> None:
    """Importa uma planilha do ERP."""
    from app.importacao.servico import analisar, gravar

    arquivo = Path(caminho)
    usuario = None
    if email:
        usuario = db.session.scalars(
            select(Usuario).where(func.lower(Usuario.email) == email.lower())
        ).first()
        if usuario is None:
            raise click.ClickException(f"{email} nao existe")

    resultado = analisar(db.session, arquivo, arquivo_nome=arquivo.name)

    click.echo(f"{len(resultado.linhas)} lancamentos")
    click.echo(f"{resultado.ignoradas} linhas de subtotal ignoradas")
    click.echo(f"{len(resultado.erros)} linhas com erro")
    click.echo(f"{resultado.divergentes} divergencias")
    click.echo(f"total baixado: {resultado.total_baixado}")
    click.echo(f"a criar: {resultado.a_criar} | a atualizar: {resultado.a_atualizar}")

    for erro in resultado.erros[:10]:
        click.echo(f"  linha {erro.linha}: {erro.campo} — {erro.mensagem}")

    if previa:
        click.echo("\n(previa: nada foi gravado)")
        return

    importacao = gravar(db.session, resultado, usuario=usuario)
    total = db.session.scalar(select(func.count()).select_from(Despesa))
    click.echo(
        f"\ngravado: {importacao.criados} criados, {importacao.atualizados} atualizados"
    )
    click.echo(f"o banco tem agora {total} despesas")
