"""Múltipla escolha nos filtros, agrupamento por ano e ação em lote."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models import Despesa

pytestmark = pytest.mark.integration


def divergentes(db) -> list[Despesa]:
    return list(db.session.scalars(select(Despesa).where(Despesa.divergente)))


# --- filtro com vários valores ---------------------------------------------


def test_duas_naturezas_somam_as_duas(entrar, leitor, carregado):
    cliente = entrar(leitor)
    uma = cliente.get("/despesas?natureza=COMBUSTIVEL").get_data(as_text=True)
    outra = cliente.get("/despesas?natureza=TICKET ALIMENTAÇÃO").get_data(as_text=True)
    juntas = cliente.get(
        "/despesas?natureza=COMBUSTIVEL&natureza=TICKET ALIMENTAÇÃO"
    ).get_data(as_text=True)

    assert uma.count('<tr class="linha-divergente"') + uma.count("<tr>") > 0
    # 5 de combustível + 4 de ticket; o que importa é a soma bater.
    assert juntas.count("<td>") > max(uma.count("<td>"), outra.count("<td>"))


def test_cada_valor_vira_um_chip_no_formulario(entrar, leitor, carregado):
    corpo = entrar(leitor).get(
        "/despesas?natureza=COMBUSTIVEL&natureza=TICKET ALIMENTAÇÃO"
    ).get_data(as_text=True)
    assert corpo.count('class="chip-escolhido"') == 2
    assert "COMBUSTIVEL" in corpo and "TICKET ALIMENTAÇÃO" in corpo


def test_cada_valor_vira_um_chip_removivel_no_painel(entrar, leitor, carregado):
    corpo = entrar(leitor).get(
        "/?natureza=COMBUSTIVEL&natureza=TICKET ALIMENTAÇÃO"
    ).get_data(as_text=True)
    assert corpo.count('class="chip"') == 2


def test_escolhidos_voltam_como_hidden_no_formulario(entrar, leitor, carregado):
    corpo = entrar(leitor).get(
        "/despesas?fornecedor=LOCALIZA RENT A CAR SA"
    ).get_data(as_text=True)
    assert 'type="hidden" name="fornecedor" value="LOCALIZA RENT A CAR SA"' in corpo


def links_de_relatorio(corpo: str) -> list[tuple[str, str]]:
    import re

    return re.findall(r'relatorios/(xlsx|pdf)\?([^"]*)', corpo)


def test_link_do_excel_leva_os_dois_valores(entrar, leitor, carregado):
    corpo = entrar(leitor).get(
        "/despesas?natureza=COMBUSTIVEL&natureza=TICKET ALIMENTAÇÃO"
    ).get_data(as_text=True)
    for _, query in links_de_relatorio(corpo):
        assert query.count("natureza=") == 2


def test_link_de_relatorio_vem_no_trecho_do_htmx(entrar, leitor, carregado):
    """O filtro troca só o #resultado. Com os botões fora dele, eles ficavam com
    o recorte de quando a página carregou — e o PDF saía com tudo."""
    corpo = entrar(leitor).get(
        "/despesas?natureza=COMBUSTIVEL", headers={"HX-Request": "true"}
    ).get_data(as_text=True)

    links = links_de_relatorio(corpo)
    assert {formato for formato, _ in links} == {"xlsx", "pdf"}
    for _, query in links:
        assert "natureza=COMBUSTIVEL" in query


def test_excel_gerado_tem_so_o_recorte(entrar, leitor, carregado):
    from io import BytesIO

    from openpyxl import load_workbook

    cliente = entrar(leitor)

    def linhas(query: str) -> int:
        livro = load_workbook(BytesIO(cliente.get("/relatorios/xlsx" + query).data))
        return sum(1 for linha in livro.active.iter_rows(min_row=2) if linha[0].value)

    assert linhas("?natureza=COMBUSTIVEL") < linhas("")


def test_relatorio_respeita_os_dois_valores(entrar, leitor, carregado):
    resposta = entrar(leitor).get(
        "/relatorios/?natureza=COMBUSTIVEL&natureza=TICKET ALIMENTAÇÃO"
    )
    assert resposta.status_code == 200
    assert b"COMBUSTIVEL" in resposta.data


# --- agrupamento por ano ----------------------------------------------------


def test_agrupar_por_ano(entrar, leitor, carregado):
    resposta = entrar(leitor).get("/despesas?agrupar=ano")
    assert resposta.status_code == 200
    assert "2026" in resposta.get_data(as_text=True)


def test_ano_soma_tudo_num_grupo_so(carregado):
    from app.despesas.filtros import Filtro, agrupar

    grupos = agrupar(carregado.session, Filtro(), por="ano")
    total = carregado.session.scalar(select(func.count(Despesa.id)))
    assert sum(grupo.quantidade for grupo in grupos) == total


# --- ação em lote -----------------------------------------------------------


def test_lote_marca_varias(entrar, operador, carregado):
    alvos = divergentes(carregado)[:3]
    ids = [str(d.id) for d in alvos]

    resposta = entrar(operador).post(
        "/despesas/divergencia-em-lote",
        data={"ids": ids, "acao": "ignorar"},
        follow_redirects=True,
    )
    assert resposta.status_code == 200
    for despesa in alvos:
        assert carregado.session.get(Despesa, despesa.id).divergencia_ignorada is True


def test_lote_desmarca(entrar, operador, carregado):
    alvos = divergentes(carregado)[:2]
    for despesa in alvos:
        despesa.divergencia_ignorada = True
    carregado.session.commit()

    entrar(operador).post(
        "/despesas/divergencia-em-lote",
        data={"ids": [str(d.id) for d in alvos], "acao": "comparar"},
        follow_redirects=True,
    )
    for despesa in alvos:
        assert carregado.session.get(Despesa, despesa.id).divergencia_ignorada is False


def test_lote_aceita_ids_de_paginas_diferentes(entrar, operador, carregado):
    """O JS manda os ids guardados; o servidor não sabe de página nenhuma."""
    todas = list(carregado.session.scalars(select(Despesa).order_by(Despesa.id)))
    alvos = [todas[0], todas[-1]]

    entrar(operador).post(
        "/despesas/divergencia-em-lote",
        data={"ids": [str(d.id) for d in alvos], "acao": "ignorar"},
        follow_redirects=True,
    )
    for despesa in alvos:
        assert carregado.session.get(Despesa, despesa.id).divergencia_ignorada is True


def test_lote_sem_selecao_avisa(entrar, operador, carregado):
    resposta = entrar(operador).post(
        "/despesas/divergencia-em-lote", data={"acao": "ignorar"}, follow_redirects=True
    )
    assert "Nenhuma despesa selecionada" in resposta.get_data(as_text=True)


def test_lote_e_negado_ao_leitor(entrar, leitor, carregado):
    alvo = divergentes(carregado)[0]
    resposta = entrar(leitor).post(
        "/despesas/divergencia-em-lote", data={"ids": [str(alvo.id)], "acao": "ignorar"}
    )
    assert resposta.status_code == 403
    assert carregado.session.get(Despesa, alvo.id).divergencia_ignorada is False


def test_lote_fica_na_auditoria_com_as_referencias(entrar, operador, carregado):
    from app.models import Auditoria

    alvos = divergentes(carregado)[:2]
    entrar(operador).post(
        "/despesas/divergencia-em-lote",
        data={"ids": [str(d.id) for d in alvos], "acao": "ignorar"},
        follow_redirects=True,
    )
    entrada = carregado.session.scalars(
        select(Auditoria).where(Auditoria.acao == "despesa.divergencia")
    ).one()
    assert entrada.payload["quantidade"] == 2
    assert entrada.payload["referencias"] == sorted(d.referencia for d in alvos)


def test_checkbox_aparece_para_operador_e_nao_para_leitor(entrar, operador, leitor, carregado):
    do_operador = entrar(operador).get("/despesas").get_data(as_text=True)
    assert "data-selecionavel" in do_operador
    assert "data-barra-selecao" in do_operador

    do_leitor = entrar(leitor).get("/despesas").get_data(as_text=True)
    assert "data-selecionavel" not in do_leitor
