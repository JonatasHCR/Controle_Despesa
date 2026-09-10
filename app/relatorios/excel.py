"""Relatorio em XLSX (XlsxWriter)."""

from __future__ import annotations

from io import BytesIO

from xlsxwriter import Workbook

CABECALHO = [
    ("Baixa", 12),
    ("Emissão", 12),
    ("Referência", 12),
    ("Fornecedor", 38),
    ("Natureza", 30),
    ("CC", 8),
    ("Documento", 16),
    ("Histórico", 52),
    ("Valor original", 16),
    ("Valor baixado", 16),
    ("Divergência", 14),
]


def gerar(despesas, resumo, *, descricao_do_filtro: str, grupos=None, titulo_do_grupo="") -> bytes:
    buffer = BytesIO()
    livro = Workbook(buffer, {"in_memory": True, "default_date_format": "dd/mm/yyyy"})

    formatos = _formatos(livro)
    _aba_lancamentos(livro, formatos, despesas, resumo, descricao_do_filtro)
    if grupos:
        _aba_resumo(livro, formatos, grupos, resumo, titulo_do_grupo)

    livro.close()
    return buffer.getvalue()


def _formatos(livro: Workbook) -> dict:
    return {
        "titulo": livro.add_format({"bold": True, "font_size": 14}),
        "filtro": livro.add_format({"font_color": "#6b6f76", "text_wrap": False}),
        "cabecalho": livro.add_format(
            {"bold": True, "bg_color": "#f4f5f7", "bottom": 1, "border_color": "#e4e5e8"}
        ),
        "data": livro.add_format({"num_format": "dd/mm/yyyy"}),
        # O R$ vem do formato de celula, e nao do texto: mandar "R$ 1.234,56"
        # como string faria o Excel tratar a coluna como texto e parar de somar.
        "moeda": livro.add_format({"num_format": 'R$ #,##0.00'}),
        "moeda_forte": livro.add_format({"num_format": 'R$ #,##0.00', "bold": True, "top": 1}),
        "texto": livro.add_format({}),
        "forte": livro.add_format({"bold": True, "top": 1}),
        "aviso": livro.add_format({"font_color": "#92400e"}),
    }


def _aba_lancamentos(livro, formatos, despesas, resumo, descricao) -> None:
    aba = livro.add_worksheet("Lançamentos")

    aba.write(0, 0, "Controle de Despesa", formatos["titulo"])
    aba.write(1, 0, descricao, formatos["filtro"])

    linha_cabecalho = 3
    for coluna, (rotulo, largura) in enumerate(CABECALHO):
        aba.write(linha_cabecalho, coluna, rotulo, formatos["cabecalho"])
        aba.set_column(coluna, coluna, largura)

    linha = linha_cabecalho + 1
    for despesa in despesas:
        aba.write_datetime(linha, 0, despesa.data_baixa, formatos["data"])
        if despesa.data_emissao:
            aba.write_datetime(linha, 1, despesa.data_emissao, formatos["data"])
        aba.write_number(linha, 2, despesa.referencia)
        aba.write_string(linha, 3, despesa.fornecedor.nome)
        aba.write_string(linha, 4, despesa.natureza.nome)
        aba.write_string(linha, 5, despesa.centro_custo.codigo)
        aba.write_string(linha, 6, despesa.documento or "")
        aba.write_string(linha, 7, despesa.historico or "")
        aba.write_number(linha, 8, float(despesa.valor_original or 0), formatos["moeda"])
        aba.write_number(linha, 9, float(despesa.valor_baixado or 0), formatos["moeda"])
        if despesa.divergente:
            aba.write_string(linha, 10, "divergente", formatos["aviso"])
        linha += 1

    aba.write_string(linha, 7, "Total", formatos["forte"])
    aba.write_number(linha, 8, float(resumo.total_original), formatos["moeda_forte"])
    aba.write_number(linha, 9, float(resumo.total_baixado), formatos["moeda_forte"])

    aba.autofilter(linha_cabecalho, 0, linha - 1, len(CABECALHO) - 1)
    aba.freeze_panes(linha_cabecalho + 1, 0)


def _aba_resumo(livro, formatos, grupos, resumo, titulo_do_grupo) -> None:
    aba = livro.add_worksheet("Resumo")
    aba.set_column(0, 0, 40)
    aba.set_column(1, 2, 18)

    for coluna, rotulo in enumerate([titulo_do_grupo or "Grupo", "Lançamentos", "Total"]):
        aba.write(0, coluna, rotulo, formatos["cabecalho"])

    linha = 1
    for grupo in grupos:
        aba.write_string(linha, 0, grupo.rotulo)
        aba.write_number(linha, 1, grupo.quantidade)
        aba.write_number(linha, 2, float(grupo.total), formatos["moeda"])
        linha += 1

    aba.write_string(linha, 0, "Total geral", formatos["forte"])
    aba.write_number(linha, 1, resumo.lancamentos, formatos["forte"])
    aba.write_number(linha, 2, float(resumo.total_baixado), formatos["moeda_forte"])
