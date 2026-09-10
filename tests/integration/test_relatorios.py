"""Relatorios em XLSX e PDF.

Os testes conferem CONTEUDO — celulas do XLSX pelo openpyxl, o HTML que vira
PDF — nunca bytes ou hash de arquivo.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.despesas.filtros import Filtro
from app.relatorios.rotas import descrever

pytestmark = pytest.mark.integration


def baixar(cliente, formato, **parametros):
    from urllib.parse import urlencode

    return cliente.get(f"/relatorios/{formato}?{urlencode(parametros, doseq=True)}")


def planilha_de(resposta):
    return load_workbook(BytesIO(resposta.data))


# --- XLSX -------------------------------------------------------------------


def test_xlsx_traz_uma_linha_por_lancamento(entrar, leitor, carregado):
    livro = planilha_de(baixar(entrar(leitor), "xlsx"))
    aba = livro["Lançamentos"]
    # 2 linhas de titulo + 1 em branco + cabecalho + 127 dados + total
    assert aba.max_row == 4 + 127 + 1


def test_xlsx_tem_o_cabecalho_esperado(entrar, leitor, carregado):
    aba = planilha_de(baixar(entrar(leitor), "xlsx"))["Lançamentos"]
    cabecalho = [celula.value for celula in aba[4]]
    assert cabecalho[:6] == ["Baixa", "Emissão", "Referência", "Fornecedor", "Natureza", "CC"]


def test_xlsx_grava_valor_como_numero_e_nao_texto(entrar, leitor, carregado):
    """Com o R$ no texto, o Excel trataria a coluna como texto e ela pararia
    de somar."""
    aba = planilha_de(baixar(entrar(leitor), "xlsx"))["Lançamentos"]
    valor = aba.cell(row=5, column=10).value
    assert isinstance(valor, int | float)
    assert "R$" in aba.cell(row=5, column=10).number_format


def test_xlsx_fecha_com_o_total(entrar, leitor, carregado):
    aba = planilha_de(baixar(entrar(leitor), "xlsx"))["Lançamentos"]
    assert aba.cell(row=aba.max_row, column=10).value == pytest.approx(442949.60)


def test_xlsx_marca_as_divergencias(entrar, leitor, carregado):
    aba = planilha_de(baixar(entrar(leitor), "xlsx"))["Lançamentos"]
    marcadas = [
        aba.cell(row=linha, column=11).value
        for linha in range(5, aba.max_row)
        if aba.cell(row=linha, column=11).value
    ]
    assert len(marcadas) == 4
    assert set(marcadas) == {"divergente"}


def test_xlsx_respeita_o_filtro(entrar, leitor, carregado):
    aba = planilha_de(baixar(entrar(leitor), "xlsx", natureza="COMBUSTIVEL"))["Lançamentos"]
    assert aba.max_row == 4 + 5 + 1


def test_xlsx_com_agrupamento_ganha_aba_de_resumo(entrar, leitor, carregado):
    livro = planilha_de(baixar(entrar(leitor), "xlsx", agrupar="natureza"))
    assert "Resumo" in livro.sheetnames
    aba = livro["Resumo"]
    assert aba.cell(row=1, column=1).value == "Natureza"
    assert aba.cell(row=aba.max_row, column=1).value == "Total geral"
    assert aba.cell(row=aba.max_row, column=3).value == pytest.approx(442949.60)


def test_subtotais_do_agrupamento_fecham_com_o_total(entrar, leitor, carregado):
    aba = planilha_de(baixar(entrar(leitor), "xlsx", agrupar="natureza"))["Resumo"]
    subtotais = [aba.cell(row=linha, column=3).value for linha in range(2, aba.max_row)]
    assert len(subtotais) == 7
    assert sum(subtotais) == pytest.approx(442949.60)


def test_xlsx_sem_agrupamento_nao_tem_resumo(entrar, leitor, carregado):
    assert "Resumo" not in planilha_de(baixar(entrar(leitor), "xlsx")).sheetnames


def test_xlsx_imprime_o_filtro_no_topo(entrar, leitor, carregado):
    aba = planilha_de(baixar(entrar(leitor), "xlsx", natureza="COMBUSTIVEL"))["Lançamentos"]
    assert "COMBUSTIVEL" in aba.cell(row=2, column=1).value


def test_xlsx_de_filtro_vazio_nao_quebra(entrar, leitor, carregado):
    resposta = baixar(entrar(leitor), "xlsx", centro="9999")
    assert resposta.status_code == 200
    assert planilha_de(resposta)["Lançamentos"].max_row == 5


# --- PDF --------------------------------------------------------------------


def test_pdf_sai_como_pdf(entrar, leitor, carregado):
    resposta = baixar(entrar(leitor), "pdf")
    assert resposta.status_code == 200
    assert resposta.data[:5] == b"%PDF-"
    assert len(resposta.data) > 5000


def test_pdf_vem_como_anexo_com_nome(entrar, leitor, carregado):
    resposta = baixar(entrar(leitor), "pdf")
    disposicao = resposta.headers["Content-Disposition"]
    assert "attachment" in disposicao
    assert disposicao.endswith('.pdf"')


def test_html_do_pdf_traz_os_lancamentos_e_o_total(app, carregado):
    """O conteudo mora no template; o WeasyPrint so o transforma em papel."""
    from flask import render_template
    from sqlalchemy import select

    from app.despesas.filtros import aplicar, totais
    from app.models import Despesa

    filtro = Filtro()
    with app.test_request_context():
        html = render_template(
            "relatorios/pdf.html",
            despesas=carregado.session.scalars(aplicar(select(Despesa), filtro)).all(),
            resumo=totais(carregado.session, filtro),
            descricao_do_filtro="Todos os lançamentos",
            grupos=None,
            titulo_do_grupo="",
        )
    assert "R$ 442.949,60" in html
    assert "ISABELA ALVES DE SOUZA" in html
    assert html.count('class="registro') == 127


def test_formato_desconhecido_da_404(entrar, leitor):
    assert entrar(leitor).get("/relatorios/docx").status_code == 404


def test_gerar_relatorio_e_auditado(entrar, leitor, carregado, db):
    from sqlalchemy import select

    from app.models import Auditoria

    baixar(entrar(leitor), "xlsx", natureza="COMBUSTIVEL")
    entrada = db.session.scalars(
        select(Auditoria).where(Auditoria.acao == "relatorio.xlsx")
    ).one()
    assert entrada.usuario_id == leitor.id
    assert entrada.payload["lancamentos"] == 5


# --- a descricao do filtro impressa no relatorio ---------------------------


def test_descricao_de_relatorio_sem_filtro():
    assert descrever(Filtro(), None).startswith("Todos os lançamentos")


def test_descricao_traz_o_periodo_e_qual_data():
    texto = descrever(Filtro(inicio=date(2026, 4, 1), fim=date(2026, 8, 31)), None)
    assert "baixa de 01/04/2026 a 31/08/2026" in texto


def test_descricao_diz_quando_o_periodo_e_por_emissao():
    texto = descrever(
        Filtro(inicio=date(2026, 4, 1), fim=date(2026, 8, 31), campo_data="data_emissao"), None
    )
    assert "emissão de" in texto


def test_descricao_junta_varios_filtros():
    texto = descrever(
        Filtro(centros=["4561"], naturezas=["COMBUSTIVEL"], somente_divergentes=True),
        "natureza",
    )
    assert "centro de custo 4561" in texto
    assert "natureza COMBUSTIVEL" in texto
    assert "somente divergentes" in texto
    assert "agrupado por natureza" in texto


def test_descricao_sempre_diz_quando_foi_emitido():
    """Sem isso, um PDF encaminhado nao diz de quando e."""
    assert "emitido em" in descrever(Filtro(), None)


def test_descricao_com_valor():
    texto = descrever(Filtro(valor_minimo=Decimal("1000")), None)
    assert "valor a partir de 1000" in texto


# --- retrato e campos completos ---------------------------------------------


def test_pdf_sai_em_retrato(app, carregado):
    """A4 retrato: 210x297mm, ou 794x1123 px CSS."""
    from sqlalchemy import select

    from app.despesas.filtros import aplicar, totais
    from app.models import Despesa
    from app.relatorios.pdf import montar

    filtro = Filtro()
    with app.test_request_context():
        documento = montar(
            carregado.session.scalars(aplicar(select(Despesa), filtro)).all(),
            totais(carregado.session, filtro),
            descricao_do_filtro="",
        )
    pagina = documento.pages[0]
    assert pagina.height > pagina.width, "saiu em paisagem"
    assert abs(pagina.width - 794) < 4
    assert abs(pagina.height - 1123) < 4


def test_pdf_repete_o_cabecalho_em_todas_as_paginas(app, carregado):
    from sqlalchemy import select

    from app.despesas.filtros import aplicar, totais
    from app.models import Despesa
    from app.relatorios.pdf import montar

    filtro = Filtro()
    with app.test_request_context():
        documento = montar(
            carregado.session.scalars(aplicar(select(Despesa), filtro)).all(),
            totais(carregado.session, filtro),
            descricao_do_filtro="",
        )
    assert len(documento.pages) > 1, "127 lançamentos deveriam passar de uma página"


def test_html_do_pdf_traz_todos_os_campos(app, carregado):
    """Emissao faltava: estava no XLSX e na tela, mas nao no PDF."""
    from flask import render_template
    from sqlalchemy import select

    from app.despesas.filtros import aplicar, totais
    from app.models import Despesa

    filtro = Filtro()
    with app.test_request_context():
        html = render_template(
            "relatorios/pdf.html",
            despesas=carregado.session.scalars(aplicar(select(Despesa), filtro)).all(),
            resumo=totais(carregado.session, filtro),
            descricao_do_filtro="Todos os lançamentos",
            grupos=None,
            titulo_do_grupo="",
        )

    for cabecalho in ("Baixa", "Emissão", "Ref.", "CC", "Documento",
                      "Fornecedor", "Natureza", "Original", "Baixado"):
        assert f">{cabecalho}<" in html, f"falta a coluna {cabecalho}"
    assert "Histórico" in html


def test_pdf_mostra_a_data_de_emissao_de_cada_lancamento(app, carregado):
    from flask import render_template
    from sqlalchemy import select

    from app.despesas.filtros import aplicar, totais
    from app.models import Despesa

    filtro = Filtro()
    with app.test_request_context():
        html = render_template(
            "relatorios/pdf.html",
            despesas=carregado.session.scalars(aplicar(select(Despesa), filtro)).all(),
            resumo=totais(carregado.session, filtro),
            descricao_do_filtro="",
            grupos=None,
            titulo_do_grupo="",
        )
    assert "06/02/2026" in html  # a emissao do primeiro lancamento


def test_pdf_explica_a_divergencia_em_numeros(app, carregado):
    from flask import render_template

    from app.despesas.filtros import totais

    with app.test_request_context():
        html = render_template(
            "relatorios/pdf.html",
            despesas=[],
            resumo=totais(carregado.session, Filtro()),
            descricao_do_filtro="",
            grupos=None,
            titulo_do_grupo="",
        )
    assert "R$ 1.002,39" in html


# --- limites do PDF ---------------------------------------------------------


def test_pdf_recusa_relatorio_grande_demais(entrar, leitor, carregado, monkeypatch):
    """O WeasyPrint leva ~50 ms por lançamento; 1200 linhas passariam de um
    minuto e prenderiam um worker. Melhor recusar cedo, com explicação."""
    from app.relatorios import pdf as modulo

    monkeypatch.setattr(modulo, "TETO_DE_LINHAS", 10)
    resposta = baixar(entrar(leitor), "pdf")
    assert resposta.status_code == 302

    corpo = entrar(leitor).get(resposta.headers["Location"]).get_data(as_text=True)
    assert "acima do limite" in corpo
    assert "Excel" in corpo


def test_excel_nao_tem_esse_limite(entrar, leitor, carregado, monkeypatch):
    from app.relatorios import pdf as modulo

    monkeypatch.setattr(modulo, "TETO_DE_LINHAS", 10)
    resposta = baixar(entrar(leitor), "xlsx")
    assert resposta.status_code == 200


def test_pdf_dentro_do_limite_sai_normalmente(entrar, leitor, carregado):
    resposta = baixar(entrar(leitor), "pdf")
    assert resposta.status_code == 200
    assert resposta.data[:5] == b"%PDF-"


def test_folhas_de_estilo_sao_parseadas_uma_vez(app, carregado):
    """O app.css custa 2,3 s de parse e não muda entre requisições."""
    from app.relatorios.pdf import _folhas_de_estilo

    with app.test_request_context():
        primeira = _folhas_de_estilo()
        segunda = _folhas_de_estilo()
    assert primeira is segunda
