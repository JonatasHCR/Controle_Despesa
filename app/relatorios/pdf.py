"""Relatorio em PDF pelo WeasyPrint.

Renderiza um template Jinja com o mesmo CSS da tela, entao nao ha um segundo
layout para manter em dia — o bloco @media print do app.css e este arquivo sao
o que difere.
"""

from __future__ import annotations

from flask import current_app, render_template

# O WeasyPrint monta o PDF em ~50 ms por lancamento — medido, e linear. Em 1200
# linhas sao 59 s, com um worker do gunicorn preso o tempo todo. O teto existe
# para a tela recusar cedo e com explicacao, em vez de estourar o timeout.
TETO_DE_LINHAS = 500


class RelatorioGrandeDemais(Exception):
    def __init__(self, quantidade: int):
        self.quantidade = quantidade
        super().__init__(
            f"O PDF sai com {quantidade} lançamentos, acima do limite de "
            f"{TETO_DE_LINHAS}. Estreite o período ou o filtro, ou use o Excel — "
            "ele não tem esse limite."
        )


def gerar(despesas, resumo, *, descricao_do_filtro: str, grupos=None, titulo_do_grupo="") -> bytes:
    if len(despesas) > TETO_DE_LINHAS:
        raise RelatorioGrandeDemais(len(despesas))
    return montar(
        despesas,
        resumo,
        descricao_do_filtro=descricao_do_filtro,
        grupos=grupos,
        titulo_do_grupo=titulo_do_grupo,
    ).write_pdf()


def _folhas_de_estilo():
    """Parseadas uma vez por processo.

    O app.css sozinho custa 2,3 s de parse, e ele nao muda entre requisicoes.
    """
    from weasyprint import CSS

    if "folhas_do_pdf" not in current_app.extensions:
        current_app.extensions["folhas_do_pdf"] = [
            CSS(filename=current_app.static_folder + "/css/app.css"),
            CSS(string=_PAGINA),
        ]
    return current_app.extensions["folhas_do_pdf"]


def montar(despesas, resumo, *, descricao_do_filtro: str, grupos=None, titulo_do_grupo=""):
    """Devolve o documento do WeasyPrint, antes de virar bytes.

    Separado do `gerar` para o teste poder conferir a pagina — orientacao e
    dimensoes — sem ter de descomprimir o PDF.
    """
    from weasyprint import HTML

    html = render_template(
        "relatorios/pdf.html",
        despesas=despesas,
        resumo=resumo,
        descricao_do_filtro=descricao_do_filtro,
        grupos=grupos,
        titulo_do_grupo=titulo_do_grupo,
    )
    return HTML(string=html, base_url=current_app.static_folder).render(
        stylesheets=_folhas_de_estilo()
    )


# Retrato. As larguras somam a area util da A4 (210mm menos 2x12mm de margem);
# o historico nao entra nesta conta porque ocupa uma linha propria.
_PAGINA = """
@page {
    size: A4 portrait;
    margin: 14mm 12mm 16mm;
    @bottom-center {
        content: "Controle de Despesa · página " counter(page) " de " counter(pages);
        font-size: 8pt;
        color: #6b6f76;
    }
}

body { font-size: 8.5pt; }

.capa { margin-bottom: 10mm; }
.capa h1 { font-size: 16pt; margin-bottom: 2mm; }

/* Os quatro indicadores em linha, sem cartao: em papel a borda so gasta tinta. */
.indicadores { display: flex; gap: 6mm; margin-bottom: 8mm; }
.indicador {
    border: none;
    border-left: 2pt solid #a61c21;
    border-radius: 0;
    padding: 0 0 0 3mm;
    flex: 1;
}
.indicador .valor { font-size: 12pt; }
.indicador .rotulo { font-size: 7pt; }
.indicador.atencao { border-left-color: #92400e; }

h2 { font-size: 10pt; margin: 6mm 0 2mm; }

table { font-size: 8pt; width: 100%; }
th, td { padding: 1.2mm 1.5mm; }
th { font-size: 6.5pt; }

/* Larguras fixas: sem elas o navegador do WeasyPrint distribui pelo conteudo e
   uma linha com fornecedor longo desloca a tabela inteira. */
.lancamentos { table-layout: fixed; }
.c-data  { width: 16mm; }
.c-ref   { width: 13mm; }
.c-cc    { width: 9mm; }
.c-doc   { width: 20mm; }
.c-forn  { width: 41mm; }
.c-nat   { width: 34mm; }
.c-valor { width: 21mm; }

.lancamentos td { white-space: normal; word-wrap: break-word; }

/* O registro e suas duas linhas nao se separam entre paginas. */
tr.registro td { border-bottom: none; }
tr.registro.sozinho td { border-bottom: 0.4pt solid #e4e5e8; }
tr.historico td {
    font-size: 7pt;
    color: #52514e;
    padding-top: 0;
    padding-bottom: 2mm;
    border-bottom: 0.4pt solid #e4e5e8;
}
tr.historico .etiqueta {
    font-size: 6pt;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #9a9ea6;
    margin-right: 1.5mm;
}

/* Divergencia: a linha inteira em ambar, para saltar na folha impressa.
   A cor nunca vem sozinha — o simbolo e a nota de rodape explicam. */
tr.registro.divergente td,
tr.historico.divergente td { background: #fef6e7; }

tr.registro.divergente td:first-child { border-left: 2pt solid #92400e; }
tr.historico.divergente td:first-child { border-left: 2pt solid #92400e; }

tr.registro.divergente td.numero { color: #92400e; font-weight: 700; }

.marca-div { color: #92400e; font-weight: 700; }

.resumo { table-layout: auto; }

tr.total-geral td { border-top: 0.8pt solid #16171a; border-bottom: none; }

.nota { margin-top: 4mm; font-size: 7.5pt; }

/* O cabecalho se repete em toda pagina; nenhum registro parte no meio. */
thead { display: table-header-group; }
tr { page-break-inside: avoid; }
"""
