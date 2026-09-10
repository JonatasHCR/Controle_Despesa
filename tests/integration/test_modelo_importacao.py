"""A planilha-modelo da importação.

O teste que importa de verdade é o último: o modelo, preenchido, tem de passar
pelo parser. Um modelo que ensina um formato que o sistema não aceita é pior que
modelo nenhum.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.importacao.modelo import ORDEM, gerar
from app.importacao.planilha import COLUNAS, COLUNAS_ESSENCIAIS, ler

pytestmark = pytest.mark.integration


@pytest.fixture
def livro():
    return load_workbook(BytesIO(gerar()))


def test_modelo_tem_as_duas_abas(livro):
    assert livro.sheetnames == ["Lançamentos", "Como preencher"]


def test_cabecalho_do_modelo_e_o_que_o_parser_espera(livro):
    """Se divergirem, o modelo ensina um formato que a importação recusa."""
    aba = livro["Lançamentos"]
    cabecalho = [celula.value for celula in aba[1]]
    assert set(cabecalho) == COLUNAS
    assert cabecalho == ORDEM


def test_modelo_traz_exemplos_preenchidos(livro):
    aba = livro["Lançamentos"]
    assert aba.max_row == 4  # cabeçalho + 3 exemplos
    assert aba.cell(row=2, column=6).value == "ISABELA ALVES DE SOUZA"


def test_um_exemplo_mostra_a_divergencia(livro):
    """A divergência é o caso que mais confunde; melhor já aparecer no modelo."""
    aba = livro["Lançamentos"]
    original = aba.cell(row=4, column=11).value
    baixado = aba.cell(row=4, column=12).value
    assert original != baixado


def test_aba_de_instrucoes_explica_cada_coluna(livro):
    aba = livro["Como preencher"]
    texto = "\n".join(
        str(celula.value)
        for linha in aba.iter_rows()
        for celula in linha
        if celula.value
    )
    for coluna in ORDEM:
        assert coluna in texto, f"a coluna {coluna} não está explicada"


def test_instrucoes_marcam_as_colunas_obrigatorias(livro):
    aba = livro["Como preencher"]
    texto = "\n".join(
        str(celula.value)
        for linha in aba.iter_rows()
        for celula in linha
        if celula.value
    )
    for coluna in COLUNAS_ESSENCIAIS:
        assert f"{coluna} (obrigatória)" in texto


def test_instrucoes_avisam_que_reimportar_sobrescreve(livro):
    aba = livro["Como preencher"]
    texto = " ".join(
        str(celula.value)
        for linha in aba.iter_rows()
        for celula in linha
        if celula.value
    )
    assert "sobrescreve" in texto
    assert "subtotal" in texto


def test_o_proprio_modelo_passa_pelo_parser(tmp_path):
    """O que fecha o ciclo: o arquivo entregue como exemplo é importável."""
    caminho = tmp_path / "modelo.xlsx"
    caminho.write_bytes(gerar())

    resultado = ler(caminho)
    assert resultado.erros == []
    assert len(resultado.linhas) == 3

    primeira = resultado.linhas[0]
    assert primeira.referencia == 136914
    assert primeira.fornecedor == "ISABELA ALVES DE SOUZA"
    assert str(primeira.valor_baixado) == "693.00"  # o negativo do modelo vira positivo

    divergente = resultado.linhas[2]
    assert divergente.divergente is True


def test_rota_do_modelo_entrega_o_arquivo(entrar, operador):
    resposta = entrar(operador).get("/importacao/modelo")
    assert resposta.status_code == 200
    assert "modelo-importacao-despesas.xlsx" in resposta.headers["Content-Disposition"]
    assert load_workbook(BytesIO(resposta.data)).sheetnames[0] == "Lançamentos"


def test_leitor_nao_baixa_o_modelo(entrar, leitor):
    assert entrar(leitor).get("/importacao/modelo").status_code == 403


def test_tela_de_importacao_oferece_o_modelo(entrar, operador):
    corpo = entrar(operador).get("/importacao/").get_data(as_text=True)
    assert "/importacao/modelo" in corpo
