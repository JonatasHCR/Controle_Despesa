"""Marcar uma despesa para parar de comparar original com baixado.

Serve para a baixa parcial que ainda vai crescer: a diferença é esperada e
sinalizá-la só polui a tela.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.despesas.filtros import Filtro, aplicar, totais
from app.models import Despesa

pytestmark = pytest.mark.integration


def uma_divergente(db) -> Despesa:
    return db.session.scalars(select(Despesa).where(Despesa.divergente)).first()


def quantas_divergentes(db) -> int:
    return db.session.scalar(select(func.count(Despesa.id)).where(Despesa.divergente))


def test_marcada_sai_da_contagem(carregado):
    antes = quantas_divergentes(carregado)
    uma_divergente(carregado).divergencia_ignorada = True
    carregado.session.commit()
    assert quantas_divergentes(carregado) == antes - 1


def test_marcada_nao_mexe_nos_valores(carregado):
    despesa = uma_divergente(carregado)
    original, baixado = despesa.valor_original, despesa.valor_baixado

    despesa.divergencia_ignorada = True
    carregado.session.commit()

    assert (despesa.valor_original, despesa.valor_baixado) == (original, baixado)
    assert despesa.diverge_nos_valores is True
    assert despesa.divergente is False


def test_desmarcar_devolve_a_sinalizacao(carregado):
    antes = quantas_divergentes(carregado)
    despesa = uma_divergente(carregado)

    despesa.divergencia_ignorada = True
    carregado.session.commit()
    despesa.divergencia_ignorada = False
    carregado.session.commit()

    assert quantas_divergentes(carregado) == antes


def test_some_do_filtro_somente_divergentes(carregado):
    despesa = uma_divergente(carregado)
    referencia = despesa.referencia
    despesa.divergencia_ignorada = True
    carregado.session.commit()

    encontradas = carregado.session.scalars(
        aplicar(select(Despesa), Filtro(somente_divergentes=True))
    ).all()
    assert referencia not in {d.referencia for d in encontradas}


def test_resumo_do_painel_acompanha(carregado):
    antes = totais(carregado.session, Filtro()).divergentes
    uma_divergente(carregado).divergencia_ignorada = True
    carregado.session.commit()
    assert totais(carregado.session, Filtro()).divergentes == antes - 1


# --- pela tela --------------------------------------------------------------


def test_operador_alterna_pela_lista(entrar, operador, carregado):
    despesa = uma_divergente(carregado)
    resposta = entrar(operador).post(
        f"/despesas/{despesa.id}/divergencia", follow_redirects=True
    )
    assert resposta.status_code == 200
    assert carregado.session.get(Despesa, despesa.id).divergencia_ignorada is True


def test_leitor_nao_alterna(entrar, leitor, carregado):
    despesa = uma_divergente(carregado)
    resposta = entrar(leitor).post(f"/despesas/{despesa.id}/divergencia")
    assert resposta.status_code == 403
    assert carregado.session.get(Despesa, despesa.id).divergencia_ignorada is False


def test_alternar_fica_na_auditoria(entrar, operador, carregado):
    from app.models import Auditoria

    despesa = uma_divergente(carregado)
    entrar(operador).post(f"/despesas/{despesa.id}/divergencia", follow_redirects=True)

    entrada = carregado.session.scalars(
        select(Auditoria).where(Auditoria.acao == "despesa.divergencia")
    ).one()
    assert entrada.usuario_id == operador.id
    assert entrada.payload["divergencia_ignorada"] is True


def test_linha_marcada_perde_o_destaque_na_tabela(entrar, operador, carregado):
    despesa = uma_divergente(carregado)
    referencia = despesa.referencia
    despesa.divergencia_ignorada = True
    carregado.session.commit()

    # Filtra pela referência: sem isso ela pode cair na página 2 e o teste passa
    # por ausência, não por acerto.
    corpo = entrar(operador).get(f"/despesas?referencia={referencia}").get_data(as_text=True)
    assert f"<td>{referencia}</td>" in corpo
    pedaco = corpo.split(f"<td>{referencia}</td>")[0]
    assert "linha-divergente" not in pedaco[pedaco.rfind("<tr") :]
    # O rótulo é escolha de texto; o contrato é o selo de aviso sumir e a
    # diferença continuar consultável.
    assert "selo-diferenca" not in corpo
    assert "não sinalizada por escolha" in corpo
