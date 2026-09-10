"""Pesquisa pela referência.

A referência é o número que a pessoa tem em mãos — é o que está no ERP, no
e-mail, no documento. Quem procura um lançamento digita ele, e o lugar natural
de digitar é a caixa "Buscar".
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from werkzeug.datastructures import MultiDict

from app.despesas.consulta import filtro_da_query
from app.despesas.filtros import Filtro, aplicar
from app.models import Despesa

pytestmark = pytest.mark.integration


def buscar(db, **parametros):
    filtro = filtro_da_query(MultiDict(parametros), sessao=db.session)
    return db.session.scalars(aplicar(select(Despesa), filtro)).all()


# --- a caixa "Buscar" alcança a referência ----------------------------------


def test_busca_livre_acha_pela_referencia_inteira(carregado):
    achadas = buscar(carregado, busca="136914")
    assert [d.referencia for d in achadas] == [136914]


def test_busca_livre_acha_por_pedaco_da_referencia(carregado):
    """Quem lembra só do começo do número também precisa achar."""
    achadas = buscar(carregado, busca="1375")
    assert len(achadas) > 1
    assert all("1375" in str(d.referencia) for d in achadas)


def test_busca_livre_continua_achando_pelo_historico(carregado):
    assert len(buscar(carregado, busca="COMBUSTIVEL UFC JOCKEY")) == 1


def test_busca_livre_continua_achando_pelo_fornecedor(carregado):
    assert buscar(carregado, busca="LOCALIZA")


def test_busca_livre_continua_achando_pelo_documento(carregado):
    assert buscar(carregado, busca="0000005540")


def test_referencia_inexistente_na_busca_livre(carregado):
    assert buscar(carregado, busca="999999") == []


# --- o campo dedicado aceita pedaço -----------------------------------------


def test_campo_referencia_com_o_numero_inteiro(carregado):
    achadas = buscar(carregado, referencia="136914")
    assert [d.referencia for d in achadas] == [136914]


def test_campo_referencia_com_pedaco(carregado):
    achadas = buscar(carregado, referencia="1375")
    assert len(achadas) > 1
    assert all("1375" in str(d.referencia) for d in achadas)


def test_campo_referencia_com_pedaco_unico(carregado):
    """Prefixo que só uma referência tem devolve exatamente ela."""
    achadas = buscar(carregado, referencia="1369")
    assert [d.referencia for d in achadas] == [136914]


def test_campo_referencia_aceita_inteiro_como_antes(carregado):
    """Chamada programática com int continua valendo."""
    filtro = Filtro(referencia=136914)
    achadas = carregado.session.scalars(aplicar(select(Despesa), filtro)).all()
    assert len(achadas) == 1


def test_campo_referencia_com_texto_qualquer_nao_quebra(carregado):
    assert buscar(carregado, referencia="abc") == []


def test_campo_referencia_vazio_nao_filtra(carregado):
    assert len(buscar(carregado, referencia="")) == 127


# --- pela tela --------------------------------------------------------------


def test_busca_pela_referencia_no_painel(entrar, leitor, carregado):
    """O painel não tem o campo dedicado; a caixa Buscar precisa dar conta."""
    corpo = entrar(leitor).get("/?busca=136914").get_data(as_text=True)
    assert "em 1 lançamento" in corpo


def test_busca_pela_referencia_na_lista(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/despesas?busca=136914").get_data(as_text=True)
    assert "<td>136914</td>" in corpo


def test_placeholder_avisa_que_a_referencia_entra_na_busca(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/despesas").get_data(as_text=True)
    assert "referência" in corpo.lower()


def test_relatorio_tambem_filtra_por_referencia(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/relatorios/?busca=136914").get_data(as_text=True)
    assert "R$ 693,00" in corpo


def test_descricao_do_relatorio_cita_a_referencia_buscada(carregado):
    from app.relatorios.rotas import descrever

    texto = descrever(Filtro(referencia="1369"), None)
    assert "referência 1369" in texto
