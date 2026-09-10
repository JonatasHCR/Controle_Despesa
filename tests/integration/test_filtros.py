"""Filtros, busca por campo e agrupamento.

E o coracao do sistema: "pesquisar podendo ser por cada campo". Todo campo tem
um teste proprio, mais os combinados e o escape dos curingas do LIKE.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.despesas.filtros import Filtro, agrupar, aplicar, totais
from app.importacao.servico import analisar, gravar
from app.models import Despesa

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).parent.parent / "fixtures" / "cc4561_amostra.xlsx"


@pytest.fixture
def carregado(db):
    with FIXTURE.open("rb") as arquivo:
        gravar(db.session, analisar(db.session, arquivo, arquivo_nome="cc4561.xlsx"))
    return db


def buscar(db, filtro: Filtro) -> list[Despesa]:
    return db.session.scalars(aplicar(select(Despesa), filtro)).all()


def quantos(db, filtro: Filtro) -> int:
    return len(buscar(db, filtro))


# --- sem filtro -------------------------------------------------------------


def test_sem_filtro_traz_tudo(carregado):
    assert quantos(carregado, Filtro()) == 127


# --- periodo ----------------------------------------------------------------


def test_periodo_por_data_de_baixa(carregado):
    filtro = Filtro(inicio=date(2026, 3, 1), fim=date(2026, 3, 31))
    achadas = buscar(carregado, filtro)
    assert len(achadas) == 4
    assert all(d.data_baixa.month == 3 for d in achadas)


def test_periodo_por_data_de_emissao(carregado):
    """O usuario escolhe qual data manda; sao periodos diferentes."""
    por_baixa = quantos(carregado, Filtro(inicio=date(2026, 3, 1), fim=date(2026, 3, 31)))
    por_emissao = quantos(
        carregado,
        Filtro(inicio=date(2026, 3, 1), fim=date(2026, 3, 31), campo_data="data_emissao"),
    )
    assert por_baixa != por_emissao


def test_periodo_e_inclusivo_nas_duas_pontas(carregado):
    um_dia = Filtro(inicio=date(2026, 3, 9), fim=date(2026, 3, 9))
    assert quantos(carregado, um_dia) == 1


def test_so_inicio_ou_so_fim(carregado):
    assert quantos(carregado, Filtro(inicio=date(2026, 8, 1))) == 29
    assert quantos(carregado, Filtro(fim=date(2026, 3, 31))) == 4


# --- centro de custo, natureza, fornecedor ---------------------------------


def test_por_centro_de_custo(carregado):
    assert quantos(carregado, Filtro(centros=["4561"])) == 127
    assert quantos(carregado, Filtro(centros=["9999"])) == 0


def test_por_natureza(carregado):
    assert quantos(carregado, Filtro(naturezas=["SERVIÇOS ESPECIALIZADOS MEI"])) == 78
    assert quantos(carregado, Filtro(naturezas=["COMBUSTIVEL"])) == 5


def test_natureza_aceita_varias(carregado):
    filtro = Filtro(naturezas=["COMBUSTIVEL", "TICKET ALIMENTAÇÃO"])
    assert quantos(carregado, filtro) == 9


def test_natureza_usa_igualdade_e_nao_prefixo(carregado):
    """'SERVIÇOS DE ORÇAMENTO' nao pode arrastar 'SERVIÇOS DIVERSOS'."""
    assert quantos(carregado, Filtro(naturezas=["SERVIÇOS DE ORÇAMENTO"])) == 1


def test_por_fornecedor(carregado):
    assert quantos(carregado, Filtro(fornecedores=["LOCALIZA RENT A CAR S/A"])) > 0


# --- campos textuais --------------------------------------------------------


def test_por_documento(carregado):
    achadas = buscar(carregado, Filtro(documento="00000038/A"))
    assert [d.referencia for d in achadas] == [136914]


def test_documento_e_busca_parcial(carregado):
    assert quantos(carregado, Filtro(documento="0000005540")) == 1


def test_por_referencia(carregado):
    achadas = buscar(carregado, Filtro(referencia=136914))
    assert len(achadas) == 1
    assert achadas[0].valor_baixado == Decimal("693.00")


def test_busca_livre_no_historico(carregado):
    assert quantos(carregado, Filtro(busca="COMBUSTIVEL UFC JOCKEY")) == 1


def test_busca_livre_alcanca_o_fornecedor(carregado):
    """Quem digita 'localiza' na busca espera achar pelo fornecedor tambem."""
    assert quantos(carregado, Filtro(busca="LOCALIZA")) > 0


def test_busca_ignora_a_caixa(carregado):
    assert quantos(carregado, Filtro(busca="localiza")) == quantos(
        carregado, Filtro(busca="LOCALIZA")
    )


def test_porcento_na_busca_e_literal(carregado):
    """Sem escapar, '%' viraria curinga e traria as 127 linhas."""
    assert quantos(carregado, Filtro(busca="%")) == 0


def test_underline_na_busca_e_literal(carregado):
    assert quantos(carregado, Filtro(busca="_")) == 0


# --- valores e divergencia --------------------------------------------------


def test_faixa_de_valor(carregado):
    achadas = buscar(carregado, Filtro(valor_minimo=Decimal("10000")))
    assert all(d.valor_baixado >= Decimal("10000") for d in achadas)
    assert len(achadas) > 0


def test_faixa_de_valor_com_teto(carregado):
    achadas = buscar(carregado, Filtro(valor_maximo=Decimal("1000")))
    assert all(d.valor_baixado <= Decimal("1000") for d in achadas)


def test_somente_divergentes(carregado):
    achadas = buscar(carregado, Filtro(somente_divergentes=True))
    assert len(achadas) == 4
    assert {d.referencia for d in achadas} == {139049, 140748, 140538, 141402}


def test_editar_valor_entra_e_sai_do_filtro_de_divergentes(carregado):
    """Sem flag armazenada, nao ha recalculo a esquecer."""
    filtro = Filtro(somente_divergentes=True)
    assert quantos(carregado, filtro) == 4

    despesa = carregado.session.scalars(
        select(Despesa).where(Despesa.referencia == 136914)
    ).one()
    despesa.valor_baixado = Decimal("999.00")
    carregado.session.commit()
    assert quantos(carregado, filtro) == 5

    despesa.valor_baixado = despesa.valor_original
    carregado.session.commit()
    assert quantos(carregado, filtro) == 4


# --- combinacoes ------------------------------------------------------------


def test_filtros_se_somam(carregado):
    filtro = Filtro(
        inicio=date(2026, 4, 1),
        fim=date(2026, 8, 31),
        centros=["4561"],
        naturezas=["COMBUSTIVEL"],
    )
    achadas = buscar(carregado, filtro)
    assert all(d.natureza.nome == "COMBUSTIVEL" for d in achadas)
    assert all(date(2026, 4, 1) <= d.data_baixa <= date(2026, 8, 31) for d in achadas)


def test_filtro_sem_resultado_devolve_lista_vazia(carregado):
    filtro = Filtro(naturezas=["COMBUSTIVEL"], fornecedores=["ISABELA ALVES DE SOUZA"])
    assert buscar(carregado, filtro) == []


# --- totais -----------------------------------------------------------------


def test_totais_respeitam_o_filtro(carregado):
    resumo = totais(carregado.session, Filtro())
    assert resumo.lancamentos == 127
    assert resumo.total_baixado == Decimal("442949.60")
    assert resumo.total_original == Decimal("441947.21")
    assert resumo.fornecedores == 33
    assert resumo.divergentes == 4


def test_totais_de_um_recorte(carregado):
    resumo = totais(carregado.session, Filtro(naturezas=["COMBUSTIVEL"]))
    assert resumo.lancamentos == 5
    assert resumo.total_baixado < Decimal("442949.60")


def test_totais_de_filtro_vazio_nao_quebram(carregado):
    resumo = totais(carregado.session, Filtro(centros=["9999"]))
    assert resumo.lancamentos == 0
    assert resumo.total_baixado == Decimal("0.00")
    assert resumo.divergentes == 0


# --- agrupamento ------------------------------------------------------------


def test_agrupar_por_natureza(carregado):
    linhas = agrupar(carregado.session, Filtro(), por="natureza")
    assert len(linhas) == 7
    assert linhas[0].rotulo == "SERVIÇOS ESPECIALIZADOS MEI"  # maior primeiro
    assert sum(linha.total for linha in linhas) == Decimal("442949.60")


def test_agrupar_por_mes_sai_em_ordem_cronologica(carregado):
    """Ordem por valor aqui poria julho antes de marco."""
    linhas = agrupar(carregado.session, Filtro(), por="mes")
    assert [linha.rotulo for linha in linhas] == [
        "03/2026", "04/2026", "05/2026", "06/2026", "07/2026", "08/2026",
    ]


def test_agrupar_por_fornecedor(carregado):
    linhas = agrupar(carregado.session, Filtro(), por="fornecedor")
    assert len(linhas) == 33
    assert sum(linha.quantidade for linha in linhas) == 127


def test_agrupar_por_centro(carregado):
    linhas = agrupar(carregado.session, Filtro(), por="centro")
    assert len(linhas) == 1
    assert linhas[0].rotulo == "4561"


def test_agrupamento_respeita_o_filtro(carregado):
    linhas = agrupar(carregado.session, Filtro(naturezas=["COMBUSTIVEL"]), por="natureza")
    assert len(linhas) == 1
    assert linhas[0].quantidade == 5


def test_agrupamento_desconhecido_e_recusado(carregado):
    with pytest.raises(ValueError, match="agrupamento"):
        agrupar(carregado.session, Filtro(), por="cor_favorita")


# --- ordenacao --------------------------------------------------------------


def test_ordem_padrao_e_por_data_de_baixa(carregado):
    achadas = buscar(carregado, Filtro())
    datas = [d.data_baixa for d in achadas]
    assert datas == sorted(datas)


def test_ordenar_por_valor_decrescente(carregado):
    achadas = buscar(carregado, Filtro(ordem="valor", decrescente=True))
    valores = [d.valor_baixado for d in achadas]
    assert valores == sorted(valores, reverse=True)


def test_campo_de_ordenacao_desconhecido_e_recusado(carregado):
    """A ordenacao vem da query string; nao pode virar SQL arbitrario."""
    with pytest.raises(ValueError, match="ordena"):
        buscar(carregado, Filtro(ordem="; DROP TABLE tb_despesas"))
