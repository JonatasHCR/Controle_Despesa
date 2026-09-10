"""Fixtures da suite de integracao.

O banco e um PostgreSQL de verdade (servico `db-test` do compose). A busca por
campo e os agrupamentos dependem de ILIKE, date_trunc e IS DISTINCT FROM se
comportando como em producao.

Isolamento por TRUNCATE, e nao por transacao aninhada: o schema e pequeno e nao
depende de detalhe interno do SQLAlchemy.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from app.extensions import db as _db
from app.factory import create_app

FIXTURE = Path(__file__).parent.parent / "fixtures" / "cc4561_amostra.xlsx"


@pytest.fixture(scope="session")
def app():
    aplicacao = create_app("test")
    with aplicacao.app_context():
        _db.create_all()
        yield aplicacao
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def db(app):
    with app.app_context():
        yield _db
        _db.session.rollback()
        _limpar(_db)


def _limpar(banco) -> None:
    tabelas = [t.name for t in banco.metadata.sorted_tables]
    if not tabelas:
        return
    alvo = ", ".join(f'"{nome}"' for nome in tabelas)
    banco.session.execute(text(f"TRUNCATE {alvo} RESTART IDENTITY CASCADE"))
    banco.session.commit()


@pytest.fixture
def client(app, db):
    return app.test_client()


# --- usuarios por perfil ----------------------------------------------------


def _criar(db, perfil: str):
    from app.models import Usuario

    usuario = Usuario(
        nome=perfil.capitalize(),
        email=f"{perfil}@ufcengenharia.com.br",
        perfil=perfil,
        external_id=f"sub-{perfil}",
    )
    db.session.add(usuario)
    db.session.commit()
    return usuario


@pytest.fixture
def leitor(db):
    return _criar(db, "leitor")


@pytest.fixture
def operador(db):
    return _criar(db, "operador")


@pytest.fixture
def admin(db):
    return _criar(db, "admin")


@pytest.fixture
def entrar(client):
    """Coloca o usuario na sessao, pulando a ida ao Keycloak."""

    def logar(usuario, grupos=("/apps/controle-despesa",)):
        with client.session_transaction() as sessao:
            sessao["usuario_id"] = usuario.id
            sessao["grupos"] = list(grupos)
        return client

    return logar


@pytest.fixture
def carregado(db):
    """Base com as 127 despesas do arquivo real."""
    from app.importacao.servico import analisar, gravar

    with FIXTURE.open("rb") as arquivo:
        gravar(db.session, analisar(db.session, arquivo, arquivo_nome="cc4561.xlsx"))
    return db
