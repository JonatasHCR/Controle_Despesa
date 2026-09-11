"""Parser da planilha do ERP.

Funcao pura: entra um arquivo, sai uma lista de linhas e uma lista de erros.
Sem Flask, sem banco — por isso e a peca que da para cravar em teste primeiro,
e e onde mora quase toda a regra chata do formato.

A fixture e o arquivo real (cc4561.xlsx), com as 168 linhas que ele tem de
verdade: 127 lancamentos e 39 subtotais do Excel.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.importacao.planilha import (
    ErroLinha,
    eh_linha_de_total,
    ler,
    normalizar_texto,
    serial_para_data,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "cc4561_amostra.xlsx"

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def resultado():
    return ler(FIXTURE)


# --- o descarte dos subtotais ----------------------------------------------


def test_descarta_as_39_linhas_de_subtotal(resultado):
    """O pedido explicito: 'tem muitos totais no arquivo, nao precisa desses totais tudo'."""
    assert len(resultado.linhas) == 127
    assert resultado.ignoradas == 39


@pytest.mark.parametrize(
    "rotulo",
    [
        "3 Total",
        "07/04/2026 00:00:00 Total",
        "14 Total",
        "4 Total",
    ],
)
def test_reconhece_as_formas_de_subtotal(rotulo):
    """O rotulo muda de coluna conforme o nivel, mas sempre termina em ' Total'."""
    celulas = [None] * 12
    celulas[1] = rotulo
    assert eh_linha_de_total(celulas) is True


def test_linha_de_lancamento_nao_e_confundida_com_subtotal():
    celulas = [
        "2026", "3", "9", "46059", "136914", "ISABELA ALVES DE SOUZA", "4561",
        "SERVICOS ESPECIALIZADOS MEI", "PRESTACAO DE SERVICOS", "00000038/A",
        "-693", "-693",
    ]
    assert eh_linha_de_total(celulas) is False


def test_fornecedor_com_a_palavra_total_no_nome_nao_e_descartado():
    """'TOTAL DISTRIBUIDORA' e fornecedor, nao subtotal."""
    celulas = [
        "2026", "3", "9", "46059", "136914", "TOTAL DISTRIBUIDORA LTDA", "4561",
        "COMBUSTIVEL", "COMBUSTIVEL", "0001", "-100", "-100",
    ]
    assert eh_linha_de_total(celulas) is False


# --- conversao de data ------------------------------------------------------


@pytest.mark.parametrize(
    "serial,esperado",
    [
        (46059, date(2026, 2, 6)),   # menor DATAEMISSAO do arquivo
        (46244, date(2026, 8, 10)),  # maior
        (46119, date(2026, 4, 7)),
    ],
)
def test_serial_do_excel_vira_data(serial, esperado):
    assert serial_para_data(serial) == esperado


def test_serial_usa_a_epoca_1899_12_30():
    """1899-12-30 e o ponto que faz as contas baterem para datas modernas."""
    assert serial_para_data(1) == date(1900, 1, 1)


def test_data_baixa_e_composta_de_ano_mes_dia(resultado):
    assert resultado.linhas[0].data_baixa == date(2026, 3, 9)


def test_periodo_das_baixas_cobre_marco_a_agosto(resultado):
    datas = [linha.data_baixa for linha in resultado.linhas]
    assert min(datas) == date(2026, 3, 9)
    assert max(datas) == date(2026, 8, 20)


def test_data_de_emissao_e_convertida(resultado):
    primeira = resultado.linhas[0]
    assert primeira.data_emissao == date(2026, 2, 6)


# --- normalizacao de texto --------------------------------------------------


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("PRESTACAO DE SERVICOS NO MES 03/2026 \n", "PRESTACAO DE SERVICOS NO MES 03/2026"),
        ("PRESTACAO DE SERVICOS\n\n ", "PRESTACAO DE SERVICOS"),
        ("REF   MES    03/2026", "REF MES 03/2026"),
        ("  espacos nas pontas  ", "espacos nas pontas"),
        (None, ""),
    ],
)
def test_normaliza_historico(entrada, esperado):
    assert normalizar_texto(entrada) == esperado


def test_nenhum_historico_sai_com_quebra_de_linha(resultado):
    """Quebra de linha no historico vira linha em branco na tabela e no PDF."""
    assert all("\n" not in linha.historico for linha in resultado.linhas)
    assert all(linha.historico == linha.historico.strip() for linha in resultado.linhas)


# --- valores ----------------------------------------------------------------


def test_valores_sao_gravados_positivos(resultado):
    """O ERP exporta tudo negativo."""
    assert all(linha.valor_baixado > 0 for linha in resultado.linhas)
    assert all(linha.valor_original > 0 for linha in resultado.linhas)


def test_somas_batem_com_as_do_arquivo(resultado):
    """Os dois totais divergem em R$ 1.002,39; o painel exibe o BAIXADO."""
    assert sum(linha.valor_baixado for linha in resultado.linhas) == Decimal("442949.60")
    assert sum(linha.valor_original for linha in resultado.linhas) == Decimal("441947.21")


def test_valores_sao_decimal_com_no_maximo_duas_casas(resultado):
    """float aqui viraria 2556.0500000000002 no relatorio."""
    assert all(isinstance(linha.valor_baixado, Decimal) for linha in resultado.linhas)
    assert all(-linha.valor_baixado.as_tuple().exponent <= 2 for linha in resultado.linhas)


def test_as_quatro_divergencias_da_localiza_sobrevivem(resultado):
    """Divergencia nao e gravada como flag — e derivada na consulta."""
    divergentes = [
        linha for linha in resultado.linhas if linha.valor_original != linha.valor_baixado
    ]
    assert len(divergentes) == 4
    assert {linha.referencia for linha in divergentes} == {139049, 140748, 140538, 141402}
    assert all("LOCALIZA" in linha.fornecedor for linha in divergentes)


def test_valor_original_com_muitas_casas_e_arredondado_para_duas(resultado):
    """O arquivo traz -6250.7393590000001; centavo e o limite do dominio."""
    linha = next(item for item in resultado.linhas if item.referencia == 139049)
    assert linha.valor_original == Decimal("6250.74")
    assert linha.valor_baixado == Decimal("6331.26")


# --- campos de identidade ---------------------------------------------------


def test_referencia_e_unica_e_serve_de_chave_natural(resultado):
    referencias = [linha.referencia for linha in resultado.linhas]
    assert len(set(referencias)) == len(referencias) == 127
    assert min(referencias) == 136914
    assert max(referencias) == 141402


def test_documento_preserva_zeros_a_esquerda(resultado):
    """'00000038/A' e '0000005540' sao identificadores, nao numeros."""
    documentos = {linha.documento for linha in resultado.linhas}
    assert "00000038/A" in documentos
    assert "0000005540" in documentos


def test_centro_de_custo_do_arquivo(resultado):
    assert {linha.centro_custo for linha in resultado.linhas} == {"4561"}


def test_as_sete_naturezas(resultado):
    contagem = Counter(linha.natureza for linha in resultado.linhas)
    assert contagem == {
        "SERVIÇOS ESPECIALIZADOS MEI": 78,
        "SERVIÇOS ADMINISTRATIVOS": 30,
        "COMBUSTIVEL": 5,
        "LOCAÇÃO VEICULOS E EQUIPAMENTOS": 5,
        "SERVIÇOS DIVERSOS (não especificados)": 4,
        "TICKET ALIMENTAÇÃO": 4,
        "SERVIÇOS DE ORÇAMENTO": 1,
    }


def test_os_33_fornecedores(resultado):
    assert len({linha.fornecedor for linha in resultado.linhas}) == 33


def test_numero_da_linha_no_arquivo_e_preservado(resultado):
    """Serve para o erro apontar onde consertar, e para a previa citar a linha."""
    assert resultado.linhas[0].linha == 3


# --- erros ------------------------------------------------------------------


def test_arquivo_valido_nao_produz_erro(resultado):
    assert resultado.erros == []


def test_erro_aponta_o_numero_da_linha_no_arquivo(tmp_path):
    """'linha 3: REFERENCIA vazia' conserta a planilha; 'erro na importacao' abre chamado."""
    caminho = _planilha_com(tmp_path, [
        ["2026", "3", "9", 46059, None, "FORNECEDOR X", "4561",
         "COMBUSTIVEL", "hist", "0001", -100, -100],
    ])
    resultado = ler(caminho)
    assert resultado.linhas == []
    assert len(resultado.erros) == 1
    erro = resultado.erros[0]
    assert isinstance(erro, ErroLinha)
    assert erro.linha == 3  # cabecalho na 2, primeiro dado na 3
    assert erro.campo == "REFERENCIA"


def test_data_de_baixa_impossivel_vira_erro(tmp_path):
    caminho = _planilha_com(tmp_path, [
        ["2026", "2", "31", 46059, 999, "FORNECEDOR X", "4561",
         "COMBUSTIVEL", "hist", "0001", -100, -100],
    ])
    resultado = ler(caminho)
    assert resultado.linhas == []
    assert resultado.erros[0].campo == "DATA_BAIXA"


def test_valor_nao_numerico_vira_erro(tmp_path):
    caminho = _planilha_com(tmp_path, [
        ["2026", "3", "9", 46059, 999, "FORNECEDOR X", "4561",
         "COMBUSTIVEL", "hist", "0001", "nao e numero", -100],
    ])
    resultado = ler(caminho)
    assert resultado.linhas == []
    assert resultado.erros[0].campo == "VALOR ORIGINAL"


def test_uma_linha_ruim_nao_derruba_as_boas(tmp_path):
    caminho = _planilha_com(tmp_path, [
        ["2026", "3", "9", 46059, 111, "FORNECEDOR A", "4561",
         "COMBUSTIVEL", "hist", "0001", -100, -100],
        ["2026", "3", "9", 46059, None, "FORNECEDOR B", "4561",
         "COMBUSTIVEL", "hist", "0002", -200, -200],
        ["2026", "3", "9", 46059, 333, "FORNECEDOR C", "4561",
         "COMBUSTIVEL", "hist", "0003", -300, -300],
    ])
    resultado = ler(caminho)
    assert [linha.referencia for linha in resultado.linhas] == [111, 333]
    assert len(resultado.erros) == 1


def test_arquivo_que_nao_e_planilha_falha_com_mensagem_clara(tmp_path):
    caminho = tmp_path / "nao_e_xlsx.xlsx"
    caminho.write_bytes(b"isto nao e um zip")
    with pytest.raises(ValueError, match="não parece uma planilha"):
        ler(caminho)


def test_planilha_sem_as_colunas_esperadas_falha(tmp_path):
    from openpyxl import Workbook

    caminho = tmp_path / "outra_coisa.xlsx"
    livro = Workbook()
    aba = livro.active
    aba.append(["nome", "idade"])
    aba.append(["ana", 30])
    livro.save(caminho)
    with pytest.raises(ValueError, match="cabeçalho"):
        ler(caminho)


def test_aceita_um_stream_alem_de_um_caminho():
    """O upload chega como stream do Werkzeug, nao como arquivo em disco."""
    with FIXTURE.open("rb") as arquivo:
        resultado = ler(arquivo)
    assert len(resultado.linhas) == 127


# --- utilitario da suite ----------------------------------------------------

CABECALHO = [
    "ANO_BAIXA", "MES_BAIXA", "DIA_BAIXA", "DATAEMISSAO", "REFERENCIA",
    "FORNECEDOR", "CR_REDUZIDO", "NATUREZA", "HISTORICO", "DOCUMENTO",
    "VALOR ORIGINAL", "VALOR BAIXADO",
]


def _planilha_com(tmp_path, linhas):
    """Monta uma planilha no mesmo formato do ERP: linha 1 solta, cabecalho na 2."""
    from openpyxl import Workbook

    caminho = tmp_path / "amostra.xlsx"
    livro = Workbook()
    aba = livro.active
    aba.append([None] * 10 + ["Total Geral", "Total Geral"])
    aba.append(CABECALHO)
    for linha in linhas:
        aba.append(linha)
    livro.save(caminho)
    return caminho


# --- numero no formato brasileiro -------------------------------------------


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("-693,00", Decimal("693.00")),
        ("1.234,56", Decimal("1234.56")),
        ("10.003,00", Decimal("10003.00")),
        ("-6.250,74", Decimal("6250.74")),
        ("1234.56", Decimal("1234.56")),      # o formato do ERP continua valendo
        (-693, Decimal("693.00")),
        (-2556.0500000000002, Decimal("2556.05")),
        ("  -693,00  ", Decimal("693.00")),
    ],
)
def test_valor_aceita_os_dois_formatos(tmp_path, entrada, esperado):
    """Planilha preenchida a mao vem com virgula decimal."""
    caminho = _planilha_com(tmp_path, [
        ["2026", "3", "9", 46059, 1, "FORNECEDOR", "4561",
         "COMBUSTIVEL", "hist", "0001", entrada, entrada],
    ])
    resultado = ler(caminho)
    assert resultado.erros == []
    assert resultado.linhas[0].valor_baixado == esperado


# --- referencia repetida dentro do arquivo ----------------------------------
#
# REFERENCIA e unica no banco. Duas linhas com a mesma quebravam a gravacao
# inteira no commit, e o erro chegava ao usuario como 500.


def planilha_com(referencias: list[int]):
    from io import BytesIO

    from openpyxl import Workbook

    livro = Workbook()
    aba = livro.active
    aba.append([])
    aba.append(
        [
            "ANO_BAIXA", "MES_BAIXA", "DIA_BAIXA", "DATAEMISSAO", "REFERENCIA",
            "FORNECEDOR", "CR_REDUZIDO", "NATUREZA", "HISTORICO", "DOCUMENTO",
            "VALOR ORIGINAL", "VALOR BAIXADO",
        ]
    )
    for referencia in referencias:
        aba.append(
            [2026, 3, 9, 46059, referencia, "FORN X", "4561", "NAT Y", "h", "D1",
             -10.00, -10.00]
        )
    buffer = BytesIO()
    livro.save(buffer)
    buffer.seek(0)
    return buffer


def test_referencia_repetida_vira_erro():
    resultado = ler(planilha_com([501, 502, 501]))
    assert [erro.campo for erro in resultado.erros] == ["REFERENCIA"]
    assert "501" in resultado.erros[0].mensagem


def test_o_erro_aponta_as_duas_linhas():
    resultado = ler(planilha_com([501, 502, 501]))
    assert resultado.erros[0].linha == 5
    assert "linha 3" in resultado.erros[0].mensagem


def test_as_duas_copias_sao_descartadas():
    """Nem a primeira entra: nao da para adivinhar qual das duas vale."""
    resultado = ler(planilha_com([501, 502, 501]))
    assert [linha.referencia for linha in resultado.linhas] == [502]


def test_arquivo_sem_repeticao_passa_inteiro():
    resultado = ler(planilha_com([501, 502, 503]))
    assert [linha.referencia for linha in resultado.linhas] == [501, 502, 503]
    assert resultado.erros == []


# --- ponto e vírgula nos valores -------------------------------------------
#
# Célula numérica já vem desambiguada pelo Excel; texto digitado à mão não.
# Tratar os dois igual quebrava um dos lados.


def normalizado(valor):
    from decimal import ROUND_HALF_UP, Decimal

    from app.importacao.planilha import _normalizar_numero

    return str(
        Decimal(_normalizar_numero(valor))
        .copy_abs()
        .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )


@pytest.mark.parametrize(
    "valor,esperado",
    [
        (1234.56, "1234.56"),
        (1234.567, "1234.57"),
        (0.123, "0.12"),
        (1000.0, "1000.00"),
        (10003, "10003.00"),
        (-693.0, "693.00"),
    ],
)
def test_celula_numerica_vai_como_esta(valor, esperado):
    """Heurística de milhar aqui viraria 1234.567 em 1234567."""
    assert normalizado(valor) == esperado


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("1.234,56", "1234.56"),
        ("1.234.567,89", "1234567.89"),
        ("-693,00", "693.00"),
        ("0,50", "0.50"),
        ("1234.56", "1234.56"),
        ("1234,5", "1234.50"),
    ],
)
def test_texto_com_virgula_decimal(texto, esperado):
    assert normalizado(texto) == esperado


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("1.234", "1234.00"),
        ("12.345", "12345.00"),
        ("1.000", "1000.00"),
        ("1.234.567", "1234567.00"),
    ],
)
def test_texto_com_ponto_de_milhar_sem_decimais(texto, esperado):
    """Lido como decimal, 1.234 virava 1,23 — o valor sumia."""
    assert normalizado(texto) == esperado


def test_espaco_inquebravel_nao_derruba():
    assert normalizado("1\xa0234,56") == "1234.56"
