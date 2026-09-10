"""Graficos do painel: SVG gerado no servidor, sem biblioteca e sem JS.

Os testes olham a ESTRUTURA do SVG (via ElementTree), nao a string — asserir
markup literal quebra ao primeiro ajuste de espacamento e nao diz nada sobre o
grafico estar certo.

Boa parte do que esta aqui trava decisao de design registrada no plano:
uma cor so, ordem por magnitude nas barras e ordem cronologica nas colunas,
camada de hover sem JS, e rotulo escapado.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from decimal import Decimal

import pytest

from app.graficos.svg import barras_horizontais, colunas

pytestmark = pytest.mark.unit

SVG = "{http://www.w3.org/2000/svg}"

POR_NATUREZA = [
    ("SERVIÇOS ESPECIALIZADOS MEI", Decimal("258320.00")),
    ("SERVIÇOS ADMINISTRATIVOS", Decimal("97410.00")),
    ("LOCAÇÃO VEICULOS E EQUIPAMENTOS", Decimal("48900.00")),
    ("COMBUSTIVEL", Decimal("13816.65")),
    ("TICKET ALIMENTAÇÃO", Decimal("4272.00")),
    ("SERVIÇOS DIVERSOS (não especificados)", Decimal("800.72")),
    ("SERVIÇOS DE ORÇAMENTO", Decimal("430.23")),
]

POR_MES = [
    ("mar", Decimal("14043.00")),
    ("abr", Decimal("51213.00")),
    ("mai", Decimal("88120.00")),
    ("jun", Decimal("95430.00")),
    ("jul", Decimal("102300.00")),
    ("ago", Decimal("91843.60")),
]


def arvore(markup: str) -> ET.Element:
    return ET.fromstring(str(markup))


def retangulos(raiz: ET.Element) -> list[ET.Element]:
    """So as marcas de dado — descarta fundo de trilha, se houver."""
    return [r for r in raiz.iter(SVG + "rect") if r.get("class") == "marca"]


# --- a regra de cor ---------------------------------------------------------


def test_todas_as_barras_usam_a_mesma_cor():
    """Colorir por categoria faria a cor mudar de dono a cada mudanca de ranking."""
    marcas = retangulos(arvore(barras_horizontais(POR_NATUREZA)))
    assert len(marcas) == 7
    assert len({r.get("fill") for r in marcas}) == 1


def test_a_cor_vem_de_token_css_para_o_tema_trocar_junto():
    """Hex cravado no SVG nao acompanha a troca de tema."""
    marcas = retangulos(arvore(barras_horizontais(POR_NATUREZA)))
    assert marcas[0].get("fill") == "var(--viz-serie)"


def test_nao_ha_legenda_em_serie_unica():
    """Serie unica nao leva caixa de legenda: o titulo ja nomeia."""
    markup = str(barras_horizontais(POR_NATUREZA, titulo="Despesa por natureza"))
    assert "legenda" not in markup.lower()


def test_vermelho_da_marca_nao_entra_nos_dados():
    """#a61c21 fica na marca e na borda dos cartoes, como no portal."""
    markup = str(barras_horizontais(POR_NATUREZA)) + str(colunas(POR_MES))
    assert "a61c21" not in markup
    assert "--brand" not in markup


# --- ordem ------------------------------------------------------------------


def test_barras_saem_ordenadas_da_maior_para_a_menor():
    raiz = arvore(barras_horizontais(list(reversed(POR_NATUREZA))))
    larguras = [float(r.get("width")) for r in retangulos(raiz)]
    assert larguras == sorted(larguras, reverse=True)


def test_colunas_preservam_a_ordem_cronologica():
    """Serie temporal ordenada por valor vira mentira: 'julho antes de marco'."""
    raiz = arvore(colunas(POR_MES))
    rotulos = [t.text for t in raiz.iter(SVG + "text") if t.get("class") == "eixo"]
    assert rotulos == ["mar", "abr", "mai", "jun", "jul", "ago"]


# --- proporcao --------------------------------------------------------------


def test_largura_da_barra_e_proporcional_ao_valor():
    raiz = arvore(barras_horizontais(POR_NATUREZA))
    marcas = retangulos(raiz)
    maior, segunda = float(marcas[0].get("width")), float(marcas[1].get("width"))
    proporcao_esperada = float(POR_NATUREZA[1][1] / POR_NATUREZA[0][1])
    assert segunda / maior == pytest.approx(proporcao_esperada, rel=0.02)


def test_altura_da_coluna_e_proporcional_ao_valor():
    raiz = arvore(colunas(POR_MES))
    marcas = retangulos(raiz)
    alturas = {r.get("data-rotulo"): float(r.get("height")) for r in marcas}
    esperado = float(POR_MES[0][1] / POR_MES[4][1])  # mar / jul (o maior)
    assert alturas["mar"] / alturas["jul"] == pytest.approx(esperado, rel=0.02)


def test_valor_zero_nao_vira_barra_invisivel_nem_negativa():
    raiz = arvore(barras_horizontais([("A", Decimal("100")), ("B", Decimal("0"))]))
    larguras = [float(r.get("width")) for r in retangulos(raiz)]
    assert all(largura >= 0 for largura in larguras)


# --- especificacao das marcas ----------------------------------------------


def test_extremidade_do_dado_e_arredondada_em_4px():
    marcas = retangulos(arvore(barras_horizontais(POR_NATUREZA)))
    assert marcas[0].get("rx") == "4"


def test_ha_folga_entre_barras_vizinhas():
    """2px de superficie entre marcas: barras coladas leem como uma so."""
    marcas = retangulos(arvore(barras_horizontais(POR_NATUREZA)))
    primeira, segunda = marcas[0], marcas[1]
    folga = float(segunda.get("y")) - (float(primeira.get("y")) + float(primeira.get("height")))
    assert folga >= 2


# --- camada de hover, sem JS ------------------------------------------------


def test_cada_marca_tem_title_com_rotulo_e_valor_formatado():
    """<title> nativo do SVG: hover sem JS, e sobrevive ao PDF."""
    marcas = retangulos(arvore(barras_horizontais(POR_NATUREZA)))
    titulos = [m.find(SVG + "title").text for m in marcas]
    assert titulos[0] == "SERVIÇOS ESPECIALIZADOS MEI: R$ 258.320,00"
    assert all(titulo for titulo in titulos)


# --- acessibilidade ---------------------------------------------------------


def test_svg_se_anuncia_como_imagem_com_descricao():
    raiz = arvore(barras_horizontais(POR_NATUREZA, titulo="Despesa por natureza"))
    assert raiz.get("role") == "img"
    assert "Despesa por natureza" in raiz.get("aria-label")


def test_rotulo_direto_de_valor_em_cada_barra():
    """Sete barras cabem com rotulo; e o alivio para quem nao le a cor."""
    raiz = arvore(barras_horizontais(POR_NATUREZA))
    valores = [t.text for t in raiz.iter(SVG + "text") if t.get("class") == "valor"]
    assert "R$ 258.320,00" in valores


# --- robustez ---------------------------------------------------------------


def test_sem_dados_devolve_aviso_e_nao_svg_quebrado():
    markup = str(barras_horizontais([]))
    assert "sem dados" in markup.lower()
    assert "<rect" not in markup


def test_total_zero_nao_divide_por_zero():
    markup = barras_horizontais([("A", Decimal("0")), ("B", Decimal("0"))])
    assert markup  # nao levanta


def test_rotulo_com_markup_e_escapado():
    """Nome de fornecedor vem de planilha que qualquer um edita."""
    markup = str(barras_horizontais([("<script>alert(1)</script>", Decimal("10"))]))
    assert "<script>" not in markup
    assert "&lt;script&gt;" in markup


def test_rotulo_longo_e_encurtado_sem_estourar_o_desenho():
    nome = "LOCAÇÃO DE VEICULOS, EQUIPAMENTOS PESADOS E MAQUINARIO DIVERSO LTDA ME"
    raiz = arvore(barras_horizontais([(nome, Decimal("10"))]))
    rotulos = [t.text for t in raiz.iter(SVG + "text") if t.get("class") == "rotulo"]
    assert len(rotulos[0]) < len(nome)
    assert rotulos[0].endswith("…")


def test_mais_de_oito_categorias_dobra_a_cauda_em_outras():
    """Nunca se resolve 'categorias demais' desenhando mais barras minusculas."""
    muitas = [(f"NATUREZA {i}", Decimal(str(100 - i))) for i in range(20)]
    raiz = arvore(barras_horizontais(muitas, maximo=8))
    marcas = retangulos(raiz)
    assert len(marcas) == 8
    ultimo = marcas[-1].find(SVG + "title").text
    assert ultimo.startswith("Outras (13)")


# --- o valor precisa estar escrito ------------------------------------------


def test_cada_coluna_traz_o_valor_escrito():
    """Barra sem numero compara duas categorias, mas nao deixa medir nenhuma."""
    raiz = arvore(colunas(POR_MES))
    valores = [t.text for t in raiz.iter(SVG + "text") if t.get("class") == "valor"]
    assert len(valores) == len(POR_MES)
    assert "14.043,00" in valores[0]


def test_colunas_tem_linha_de_base():
    raiz = arvore(colunas(POR_MES))
    linhas = [e for e in raiz.iter(SVG + "line") if e.get("class") == "eixo-linha"]
    assert len(linhas) == 1


def test_valor_da_coluna_nao_sai_do_desenho():
    """O texto fica acima da marca; sem folga no topo, a maior sairia cortada."""
    raiz = arvore(colunas(POR_MES))
    marcas = retangulos(raiz)
    valores = [t for t in raiz.iter(SVG + "text") if t.get("class") == "valor"]
    mais_alta = min(float(m.get("y")) for m in marcas)
    mais_alto = min(float(t.get("y")) for t in valores)
    assert mais_alto > 0
    assert mais_alto < mais_alta


def test_com_muitas_colunas_o_valor_e_abreviado():
    """Doze meses com 'R$ 102.300,00' embaixo de cada um nao cabem."""
    muitos = [(f"m{i}", Decimal("102300")) for i in range(12)]
    raiz = arvore(colunas(muitos))
    valores = [t.text for t in raiz.iter(SVG + "text") if t.get("class") == "valor"]
    assert valores[0] == "102,3 mil"


def test_valor_de_milhao_e_abreviado_em_mi():
    from app.graficos.svg import _curto

    assert _curto(Decimal("2500000")) == "2,5 mi"
    assert _curto(Decimal("999")) == "999"
