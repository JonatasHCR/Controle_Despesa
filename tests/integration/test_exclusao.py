"""Excluir despesa: onde a ação fica e como ela é confirmada.

Regressão de dois bugs reais, ambos causados pela CSP fechada em
`script-src 'self'`: handler inline (`onsubmit`, `onchange`) é bloqueado, e
bloqueado em silêncio. A confirmação da exclusão nunca rodava — o botão apagava
no primeiro clique — e o seletor "Sistemas" não navegava.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import func, select

from app.models import Auditoria, Despesa

pytestmark = pytest.mark.integration


# --- nada de handler inline -------------------------------------------------


@pytest.mark.parametrize("caminho", ["/", "/despesas", "/despesas/nova"])
def test_nenhuma_pagina_usa_handler_inline(entrar, operador, carregado, caminho):
    """Com a CSP fechada, `onclick=` e companhia não executam."""
    corpo = entrar(operador).get(caminho).get_data(as_text=True)
    assert not re.search(r"\son(click|change|submit|input)\s*=", corpo)


def test_formulario_de_edicao_tambem_nao_usa(entrar, operador, carregado, db):
    despesa = db.session.scalars(select(Despesa)).first()
    corpo = entrar(operador).get(f"/despesas/{despesa.id}/editar").get_data(as_text=True)
    assert not re.search(r"\son(click|change|submit|input)\s*=", corpo)


def test_a_confirmacao_vem_por_atributo_de_dados(entrar, operador, carregado, db):
    despesa = db.session.scalars(select(Despesa)).first()
    corpo = entrar(operador).get(f"/despesas/{despesa.id}/editar").get_data(as_text=True)
    assert "data-confirmar=" in corpo
    assert "Excluir a despesa" in corpo


def test_o_seletor_de_sistemas_declara_o_comportamento(entrar, operador, carregado):
    """O seletor só aparece para quem tem acesso a outro sistema."""
    cliente = entrar(operador, grupos=["/apps/controle-despesa", "/apps/receita"])
    corpo = cliente.get("/").get_data(as_text=True)
    assert "data-ir-para" in corpo
    assert "Receita" in corpo


def test_o_script_de_acoes_e_carregado(entrar, operador, carregado):
    corpo = entrar(operador).get("/").get_data(as_text=True)
    assert "js/acoes.js" in corpo


# --- a ação está na lista, não só no formulário -----------------------------


def test_a_lista_oferece_excluir(entrar, operador, carregado):
    """Antes era preciso abrir Editar para achar a exclusão."""
    corpo = entrar(operador).get("/despesas").get_data(as_text=True)
    assert "/excluir" in corpo
    assert "Excluir" in corpo


def test_cada_linha_tem_editar_e_excluir(entrar, operador, carregado):
    corpo = entrar(operador).get("/despesas?referencia=136914").get_data(as_text=True)
    assert corpo.count("/editar") >= 1
    assert corpo.count("/excluir") == 1


def test_leitor_nao_ve_a_acao_de_excluir(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/despesas").get_data(as_text=True)
    assert "/excluir" not in corpo


def test_excluir_pela_lista_apaga_e_audita(entrar, operador, carregado, db):
    despesa = db.session.scalars(select(Despesa).where(Despesa.referencia == 136914)).one()
    identificador = despesa.id

    resposta = entrar(operador).post(
        f"/despesas/{identificador}/excluir", follow_redirects=True
    )
    assert resposta.status_code == 200
    assert db.session.get(Despesa, identificador) is None
    assert db.session.scalar(select(func.count()).select_from(Despesa)) == 126

    entrada = db.session.scalars(
        select(Auditoria).where(Auditoria.acao == "despesa.excluir")
    ).one()
    assert entrada.payload["referencia"] == 136914


def test_excluir_volta_para_a_lista_com_o_filtro(entrar, operador, carregado, db):
    """Apagar da terceira página não pode jogar a pessoa para o começo sem filtro."""
    despesa = db.session.scalars(select(Despesa).where(Despesa.referencia == 136914)).one()
    resposta = entrar(operador).post(
        f"/despesas/{despesa.id}/excluir?natureza=COMBUSTIVEL",
        follow_redirects=False,
    )
    assert "natureza=COMBUSTIVEL" in resposta.headers["Location"]


def test_excluir_o_que_nao_existe_da_404(entrar, operador):
    assert entrar(operador).post("/despesas/999999/excluir").status_code == 404


def test_leitor_nao_exclui_nem_forcando_a_url(entrar, leitor, carregado, db):
    despesa = db.session.scalars(select(Despesa)).first()
    assert entrar(leitor).post(f"/despesas/{despesa.id}/excluir").status_code == 403
    assert db.session.scalar(select(func.count()).select_from(Despesa)) == 127


# --- identidade não vaza entre requisições ----------------------------------


def test_o_usuario_nao_vaza_entre_clientes_no_mesmo_contexto(app, db, leitor, admin):
    """`g` vive no contexto de aplicação, que num script dura o processo todo.

    Sem conferir o cache contra o id da sessão, o segundo cliente herdaria o
    usuário do primeiro — e um leitor responderia como admin.
    """
    from app.auth.guardas import usuario_atual

    primeiro = app.test_client()
    with primeiro.session_transaction() as sessao:
        sessao["usuario_id"] = admin.id

    segundo = app.test_client()
    with segundo.session_transaction() as sessao:
        sessao["usuario_id"] = leitor.id

    with app.test_request_context():
        from flask import session as sessao_atual

        sessao_atual["usuario_id"] = admin.id
        assert usuario_atual().perfil == "admin"

        sessao_atual["usuario_id"] = leitor.id
        assert usuario_atual().perfil == "leitor", "o usuário anterior ficou em cache"

        del sessao_atual["usuario_id"]
        assert usuario_atual() is None
