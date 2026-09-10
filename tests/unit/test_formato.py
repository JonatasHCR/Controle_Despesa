"""Formatacao pt-BR.

Fica num modulo proprio porque os mesmos numeros saem em quatro lugares — tela,
PDF, XLSX e os rotulos do grafico — e um deles formatando diferente dos outros e
o tipo de coisa que ninguem nota ate o relatorio chegar na diretoria.

Nao se usa `locale.setlocale`: depende de locale instalado no sistema, e a
imagem e `python:3.12-slim`, que nao tem pt_BR. Formatacao explicita nao depende
de container nenhum.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.formato import data_curta, data_longa, mes_curto, moeda, numero

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "valor,esperado",
    [
        (Decimal("441947.21"), "R$ 441.947,21"),
        (Decimal("442949.60"), "R$ 442.949,60"),
        (Decimal("693"), "R$ 693,00"),
        (Decimal("1002.39"), "R$ 1.002,39"),
        (Decimal("0"), "R$ 0,00"),
        (Decimal("0.05"), "R$ 0,05"),
        (Decimal("1234567.89"), "R$ 1.234.567,89"),
    ],
)
def test_moeda(valor, esperado):
    assert moeda(valor) == esperado


def test_moeda_aceita_int_e_float():
    assert moeda(693) == "R$ 693,00"
    assert moeda(693.5) == "R$ 693,50"


def test_moeda_de_nada_nao_quebra_a_tela():
    """Celula vazia no relatorio e melhor que 500."""
    assert moeda(None) == "—"


def test_moeda_negativa_mantem_o_sinal_antes_do_simbolo():
    """Nao deveria acontecer, mas um ajuste manual pode produzir."""
    assert moeda(Decimal("-100.50")) == "-R$ 100,50"


def test_moeda_sem_simbolo_para_a_celula_do_xlsx():
    """No XLSX quem poe o R$ e o formato de celula, senao o Excel trata como texto."""
    assert moeda(Decimal("441947.21"), simbolo=False) == "441.947,21"


@pytest.mark.parametrize(
    "valor,esperado",
    [(127, "127"), (1234, "1.234"), (0, "0"), (1234567, "1.234.567")],
)
def test_numero_inteiro_com_separador_de_milhar(valor, esperado):
    assert numero(valor) == esperado


def test_datas():
    assert data_curta(date(2026, 3, 9)) == "09/03/2026"
    assert data_longa(date(2026, 3, 9)) == "9 de março de 2026"
    assert data_curta(None) == "—"


@pytest.mark.parametrize(
    "mes,esperado",
    [(1, "jan"), (3, "mar"), (8, "ago"), (12, "dez")],
)
def test_mes_curto_para_o_eixo_do_grafico(mes, esperado):
    assert mes_curto(mes) == esperado
