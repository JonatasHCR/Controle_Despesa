"""Formatacao pt-BR sem locale do sistema.

A imagem python:3.12-slim nao traz pt_BR gerado, e setlocale falha calado em
algumas plataformas.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

VAZIO = "—"  # ausencia e coisa diferente de zero

MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)

MESES_CURTOS = (
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
)

CENTAVO = Decimal("0.01")


def moeda(valor, *, simbolo: bool = True) -> str:
    """`Decimal('441947.21')` -> `'R$ 441.947,21'`.

    Com simbolo=False sai so o numero: no XLSX quem poe o R$ e o formato da
    celula, senao o Excel trata o valor como texto e a coluna para de somar.
    """
    if valor is None:
        return VAZIO

    quantia = Decimal(str(valor)).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    negativo = quantia < 0
    inteiro, _, centavos = quantia.copy_abs().__str__().partition(".")
    corpo = f"{_com_milhar(inteiro)},{(centavos or '00').ljust(2, '0')[:2]}"

    if simbolo:
        corpo = f"R$ {corpo}"
    return f"-{corpo}" if negativo else corpo


def moeda_com_sinal(valor) -> str:
    """`+861,12` / `-74,89`. Sem simbolo: e uma diferenca, nao um saldo."""
    if valor is None:
        return VAZIO
    quantia = Decimal(str(valor)).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    if quantia == 0:
        return "0,00"
    sinal = "+" if quantia > 0 else "−"  # menos tipografico, nao hifen
    return sinal + moeda(quantia.copy_abs(), simbolo=False)


def numero(valor) -> str:
    """`1234` -> `'1.234'`."""
    if valor is None:
        return VAZIO
    return _com_milhar(str(int(valor)))


def data_curta(valor: date | None) -> str:
    if valor is None:
        return VAZIO
    return f"{valor.day:02d}/{valor.month:02d}/{valor.year}"


def data_longa(valor: date | None) -> str:
    """Para o cabecalho do relatorio."""
    if valor is None:
        return VAZIO
    return f"{valor.day} de {MESES[valor.month - 1]} de {valor.year}"


def mes_curto(mes: int) -> str:
    return MESES_CURTOS[mes - 1]


def _com_milhar(inteiro: str) -> str:
    partes = []
    while len(inteiro) > 3:
        partes.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    partes.insert(0, inteiro)
    return ".".join(partes)
