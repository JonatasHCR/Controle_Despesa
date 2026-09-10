"""O destaque visual da divergência, na tela e no papel.

A cor nunca vai sozinha: ícone e rótulo continuam presentes, porque um relatório
impresso em preto e branco — ou lido por quem não distingue a cor — não pode
perder a informação.
"""

from __future__ import annotations

import pytest

from app.despesas.filtros import Filtro

pytestmark = pytest.mark.integration


def linha_da(corpo: str, referencia: int) -> str:
    """O <tr> que contém aquela referência."""
    pedaco = corpo.split(f"<td>{referencia}</td>")[0]
    return pedaco[pedaco.rfind("<tr") :]


# --- na tela ----------------------------------------------------------------


def test_linha_divergente_e_marcada_na_tabela(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/despesas?divergentes=1").get_data(as_text=True)
    assert corpo.count('class="linha-divergente"') == 4


def test_linha_normal_nao_e_marcada(entrar, leitor, carregado):
    """Uma referência por vez: assim o teste não depende de qual página ela cai."""
    cliente = entrar(leitor)
    divergente = cliente.get("/despesas?referencia=139049").get_data(as_text=True)
    normal = cliente.get("/despesas?referencia=136914").get_data(as_text=True)
    assert "linha-divergente" in divergente
    assert "linha-divergente" not in normal


def test_valores_divergentes_ganham_cor(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/despesas?divergentes=1").get_data(as_text=True)
    # Dois valores por lançamento: original e baixado.
    assert corpo.count("valor-divergente") == 8


def test_a_cor_nao_vai_sozinha(entrar, leitor, carregado):
    """Ícone e explicação continuam ao lado do valor."""
    corpo = entrar(leitor).get("/despesas?divergentes=1").get_data(as_text=True)
    assert "⚠" in corpo
    assert "divergem em" in corpo


def test_o_selo_do_resumo_continua(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/despesas").get_data(as_text=True)
    assert "4 divergentes" in corpo


def test_o_bloco_de_divergencia_do_painel_continua_marcado(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/").get_data(as_text=True)
    assert "bloco-divergencia" in corpo
    assert "bloco-divergencia limpo" not in corpo


# --- no PDF -----------------------------------------------------------------


def html_do_pdf(app, carregado):
    from flask import render_template
    from sqlalchemy import select

    from app.despesas.filtros import aplicar, totais
    from app.models import Despesa

    filtro = Filtro()
    with app.test_request_context():
        return render_template(
            "relatorios/pdf.html",
            despesas=carregado.session.scalars(aplicar(select(Despesa), filtro)).all(),
            resumo=totais(carregado.session, filtro),
            descricao_do_filtro="Todos os lançamentos",
            grupos=None,
            titulo_do_grupo="",
        )


def test_pdf_marca_as_quatro_linhas_divergentes(app, carregado):
    html = html_do_pdf(app, carregado)
    assert html.count('class="registro') == 127
    # As 4 divergentes, na linha do registro e na do histórico.
    assert html.count("divergente") >= 4


def test_pdf_marca_a_linha_do_historico_junto(app, carregado):
    """O registro tem duas linhas; destacar só a de cima parte o bloco ao meio."""
    html = html_do_pdf(app, carregado)
    assert 'class="historico divergente"' in html


def test_pdf_explica_o_simbolo_no_rodape(app, carregado):
    html = html_do_pdf(app, carregado)
    assert "⚠ divergente: o valor baixado não coincide com o original" in html
    assert "R$ 1.002,39" in html


def test_pdf_sem_divergencia_nao_marca_nada(app, db):
    from flask import render_template

    from app.despesas.filtros import totais

    with app.test_request_context():
        html = render_template(
            "relatorios/pdf.html",
            despesas=[],
            resumo=totais(db.session, Filtro()),
            descricao_do_filtro="",
            grupos=None,
            titulo_do_grupo="",
        )
    assert "⚠ divergente:" not in html


# --- a tabela cabe na tela --------------------------------------------------


def test_tabela_tem_largura_fixa_por_coluna(entrar, leitor, carregado):
    """Sem isso, o fornecedor mais longo empurra a tabela para fora da tela."""
    corpo = entrar(leitor).get("/despesas").get_data(as_text=True)
    assert 'class="lancamentos"' in corpo
    for classe in ("c-data", "c-ref", "c-cc", "c-doc", "c-forn", "c-nat",
                   "c-hist", "c-valor", "c-situacao"):
        assert classe in corpo


def test_campos_longos_cortam_com_reticencias(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/despesas").get_data(as_text=True)
    assert 'class="corta"' in corpo


def test_o_valor_inteiro_fica_no_title(entrar, leitor, carregado):
    """Cortar na tela nao pode esconder a informacao."""
    corpo = entrar(leitor).get("/despesas").get_data(as_text=True)
    assert 'title="PRESTAÇÃO DE SERVIÇOS REF MES 12/2025"' in corpo


def test_todas_as_colunas_estao_presentes(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/despesas").get_data(as_text=True)
    for cabecalho in ("Baixa", "Emissão", "Ref.", "CC", "Documento", "Fornecedor",
                      "Natureza", "Histórico", "Original", "Baixado", "Situação"):
        assert f">{cabecalho}<" in corpo


# --- a coluna Situação ------------------------------------------------------


def test_coluna_situacao_mostra_a_diferenca_com_sinal(entrar, leitor, carregado):
    """Dizer que diverge não basta; a pergunta seguinte é 'de quanto'."""
    corpo = entrar(leitor).get("/despesas?divergentes=1").get_data(as_text=True)
    assert "+80,52" in corpo     # 139049
    assert "+135,64" in corpo    # 140748
    assert "\u2212 74,89" in corpo or "\u221274,89" in corpo  # 140538, para menos
    assert "+861,12" in corpo    # 141402


def test_lancamento_normal_nao_tem_selo_de_diferenca(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/despesas?referencia=136914").get_data(as_text=True)
    assert "selo-diferenca" not in corpo
    assert "sem-nota" in corpo


def test_o_historico_continua_na_tabela(entrar, leitor, carregado):
    """Foi pedido explicitamente: todos os campos visíveis."""
    corpo = entrar(leitor).get("/despesas").get_data(as_text=True)
    assert ">Histórico<" in corpo
    assert "PRESTAÇÃO DE SERVIÇOS REF MES 12/2025" in corpo
