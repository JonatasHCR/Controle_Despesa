"""Planilha-modelo da importação.

Existe para responder "que colunas o sistema espera?" antes de alguém montar o
arquivo — em vez de descobrir pela mensagem de erro depois de tentar.

O modelo é gerado a partir das mesmas constantes que o parser usa, então ele não
tem como divergir do que a importação de fato aceita.
"""

from __future__ import annotations

from io import BytesIO

from xlsxwriter import Workbook

from app.importacao.planilha import COLUNAS_ESSENCIAIS

# Ordem em que o export do ERP entrega as colunas. O parser lê por nome, então
# a ordem aqui é só para o arquivo sair parecido com o que a pessoa já conhece.
ORDEM = [
    "ANO_BAIXA",
    "MES_BAIXA",
    "DIA_BAIXA",
    "DATAEMISSAO",
    "REFERENCIA",
    "FORNECEDOR",
    "CR_REDUZIDO",
    "NATUREZA",
    "HISTORICO",
    "DOCUMENTO",
    "VALOR ORIGINAL",
    "VALOR BAIXADO",
]

EXPLICACAO = {
    "ANO_BAIXA": ("Ano da baixa", "2026", 12),
    "MES_BAIXA": ("Mês da baixa, de 1 a 12", "3", 12),
    "DIA_BAIXA": ("Dia da baixa", "9", 12),
    "DATAEMISSAO": ("Data de emissão. Aceita data ou o número de série do Excel", "06/02/2026", 14),
    "REFERENCIA": (
        "Identificador do lançamento no ERP. É a chave: reimportar o mesmo "
        "número atualiza o lançamento em vez de duplicar",
        "136914",
        13,
    ),
    "FORNECEDOR": ("Nome do fornecedor", "ISABELA ALVES DE SOUZA", 38),
    "CR_REDUZIDO": ("Código do centro de custo", "4561", 13),
    "NATUREZA": ("O tipo da despesa", "SERVIÇOS ESPECIALIZADOS MEI", 32),
    "HISTORICO": ("Descrição livre", "PRESTAÇÃO DE SERVIÇOS REF MES 12/2025", 44),
    "DOCUMENTO": ("Número do documento. Zeros à esquerda são preservados", "00000038/A", 16),
    "VALOR ORIGINAL": (
        "Valor original. Pode vir negativo — o sistema grava o valor absoluto",
        "-693,00",
        16,
    ),
    "VALOR BAIXADO": (
        "Valor efetivamente baixado. Diferente do original, o lançamento é "
        "marcado como divergente",
        "-693,00",
        16,
    ),
}

EXEMPLOS = [
    ["2026", "3", "9", "06/02/2026", "136914", "ISABELA ALVES DE SOUZA", "4561",
     "SERVIÇOS ESPECIALIZADOS MEI", "PRESTAÇÃO DE SERVIÇOS REF MES 12/2025",
     "00000038/A", "-693,00", "-693,00"],
    ["2026", "3", "30", "30/03/2026", "137830", "TICKET SOLUCOES HDFGT S/A", "4561",
     "COMBUSTIVEL", "BENEFICIOS COMBUSTIVEL", "0000005540", "-10003,00", "-10003,00"],
    ["2026", "6", "19", "19/06/2026", "139049", "LOCALIZA RENT A CAR S/A", "4561",
     "LOCAÇÃO VEICULOS E EQUIPAMENTOS", "BOLETO LOCAÇAO", "0001090379",
     "-6250,74", "-6331,26"],
]

OBSERVACOES = [
    "O cabeçalho é procurado nas 10 primeiras linhas — não precisa estar na linha 1.",
    "As colunas são lidas pelo NOME, não pela posição: pode reordenar à vontade.",
    "Coluna a mais no arquivo é ignorada. Coluna a menos, entre as obrigatórias, recusa o arquivo.",
    "Linhas de subtotal do Excel (as que terminam em ' Total') são descartadas na leitura.",
    "Linha com problema fica de fora e é listada na prévia; as demais entram normalmente.",
    "Nada é gravado antes de você confirmar a prévia.",
    "Reimportar o mesmo arquivo atualiza os lançamentos — a planilha é a fonte, e "
    "sobrescreve edições feitas na tela.",
]


def gerar() -> bytes:
    buffer = BytesIO()
    livro = Workbook(buffer, {"in_memory": True})

    negrito = livro.add_format({"bold": True})
    cabecalho = livro.add_format(
        {"bold": True, "bg_color": "#f4f5f7", "bottom": 1, "border_color": "#e4e5e8"}
    )
    obrigatorio = livro.add_format(
        {"bold": True, "bg_color": "#f6eaea", "font_color": "#a61c21",
         "bottom": 1, "border_color": "#a61c21"}
    )
    titulo = livro.add_format({"bold": True, "font_size": 14})
    apagado = livro.add_format({"font_color": "#6b6f76", "text_wrap": True, "valign": "top"})

    _aba_dados(livro, cabecalho, obrigatorio)
    _aba_instrucoes(livro, titulo, negrito, apagado)

    livro.close()
    return buffer.getvalue()


def _aba_dados(livro, cabecalho, obrigatorio) -> None:
    aba = livro.add_worksheet("Lançamentos")

    for coluna, nome in enumerate(ORDEM):
        _descricao, _exemplo, largura = EXPLICACAO[nome]
        formato = obrigatorio if nome in COLUNAS_ESSENCIAIS else cabecalho
        aba.write(0, coluna, nome, formato)
        aba.set_column(coluna, coluna, largura)
        aba.write_comment(0, coluna, _descricao, {"width": 260, "height": 90})

    for linha, exemplo in enumerate(EXEMPLOS, start=1):
        for coluna, valor in enumerate(exemplo):
            aba.write_string(linha, coluna, valor)

    aba.freeze_panes(1, 0)


def _aba_instrucoes(livro, titulo, negrito, apagado) -> None:
    aba = livro.add_worksheet("Como preencher")
    aba.set_column(0, 0, 22)
    aba.set_column(1, 1, 78)

    aba.write(0, 0, "Modelo de importação — Controle de Despesa", titulo)

    linha = 2
    aba.write(linha, 0, "Coluna", negrito)
    aba.write(linha, 1, "O que é", negrito)
    linha += 1

    for nome in ORDEM:
        descricao, exemplo, _largura = EXPLICACAO[nome]
        obrigatoria = " (obrigatória)" if nome in COLUNAS_ESSENCIAIS else ""
        aba.write(linha, 0, nome + obrigatoria, negrito)
        aba.write(linha, 1, f"{descricao}. Exemplo: {exemplo}", apagado)
        linha += 1

    linha += 1
    aba.write(linha, 0, "Regras", negrito)
    linha += 1
    for observacao in OBSERVACOES:
        aba.write(linha, 1, "• " + observacao, apagado)
        linha += 1
