"""Os chips do recorte ativo.

Ler o filtro pelo formulário obriga a percorrer oito campos atrás do que está
preenchido. Os chips dizem o recorte numa linha, e cada um sai com um clique.
"""

from __future__ import annotations

import pytest
from werkzeug.datastructures import MultiDict

from app.despesas.consulta import chips_do_filtro

pytestmark = pytest.mark.integration


def chips(**parametros):
    return chips_do_filtro(MultiDict(parametros))


def rotulos(lista):
    return [chip.rotulo for chip in lista]


# --- o que vira chip --------------------------------------------------------


def test_sem_filtro_nao_ha_chip():
    assert chips() == []


def test_periodo_completo_vira_um_chip_so():
    """Início e fim são um recorte, não dois."""
    lista = chips(inicio="2026-03-01", fim="2026-08-31")
    assert len(lista) == 1
    assert lista[0].rotulo == "Baixa"
    assert lista[0].valor == "01/03/2026 – 31/08/2026"


def test_periodo_so_com_inicio():
    lista = chips(inicio="2026-03-01")
    assert lista[0].valor == "a partir de 01/03/2026"


def test_periodo_so_com_fim():
    lista = chips(fim="2026-08-31")
    assert lista[0].valor == "até 31/08/2026"


def test_periodo_por_emissao_muda_o_rotulo():
    lista = chips(inicio="2026-03-01", fim="2026-08-31", campo_data="data_emissao")
    assert lista[0].rotulo == "Emissão"


def test_cada_campo_de_dominio_vira_um_chip():
    lista = chips(centro="4561", natureza="COMBUSTIVEL", fornecedor="LOCALIZA")
    assert rotulos(lista) == ["Centro de custo", "Natureza", "Fornecedor"]
    assert [chip.valor for chip in lista] == ["4561", "COMBUSTIVEL", "LOCALIZA"]


def test_chip_mostra_o_termo_digitado_e_nao_o_resolvido():
    """Quem digitou "MEI" quer ver "MEI" no chip."""
    lista = chips(natureza="MEI")
    assert lista[0].valor == "MEI"


def test_busca_documento_e_referencia_viram_chips():
    lista = chips(busca="boleto", documento="0001", referencia="1369")
    assert rotulos(lista) == ["Referência", "Documento", "Busca"]


def test_faixa_de_valor_vira_um_chip():
    lista = chips(valor_minimo="1000", valor_maximo="5000")
    assert len(lista) == 1
    assert lista[0].rotulo == "Valor"
    assert lista[0].valor == "1000 – 5000"


def test_valor_so_com_minimo():
    assert chips(valor_minimo="1000")[0].valor == "a partir de 1000"


def test_divergentes_vira_chip_sem_valor():
    lista = chips(divergentes="1")
    assert lista[0].rotulo == "Somente divergentes"
    assert lista[0].valor == ""


def test_agrupamento_nao_e_filtro_e_nao_vira_chip():
    """Agrupar muda a apresentação, não o recorte."""
    assert chips(agrupar="natureza") == []


def test_pagina_e_ordem_tambem_nao_viram_chip():
    assert chips(pagina="3", ordem="valor", desc="1") == []


# --- remover um chip --------------------------------------------------------


def test_remover_um_chip_preserva_os_outros():
    lista = chips(centro="4561", natureza="COMBUSTIVEL", busca="boleto")
    natureza = next(chip for chip in lista if chip.rotulo == "Natureza")
    assert natureza.sem == {"centro": "4561", "busca": "boleto"}


def test_remover_o_periodo_tira_as_duas_pontas():
    lista = chips(inicio="2026-03-01", fim="2026-08-31", centro="4561")
    assert lista[0].sem == {"centro": "4561"}


def test_remover_a_faixa_de_valor_tira_as_duas_pontas():
    lista = chips(valor_minimo="1000", valor_maximo="5000", centro="4561")
    valor = next(chip for chip in lista if chip.rotulo == "Valor")
    assert valor.sem == {"centro": "4561"}


def test_remover_um_chip_descarta_a_pagina():
    """Sair de um filtro na página 3 poderia cair fora do resultado novo."""
    lista = chips(centro="4561", natureza="COMBUSTIVEL", pagina="3")
    natureza = next(chip for chip in lista if chip.rotulo == "Natureza")
    assert "pagina" not in natureza.sem


def test_remover_um_chip_preserva_o_agrupamento():
    lista = chips(centro="4561", agrupar="natureza")
    assert lista[0].sem == {"agrupar": "natureza"}


# --- na tela ----------------------------------------------------------------


def test_chips_aparecem_no_painel(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/?centro=4561&natureza=COMBUSTIVEL").get_data(as_text=True)
    assert "Centro de custo" in corpo
    assert "chip" in corpo


def test_sem_filtro_o_painel_nao_mostra_chips(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/").get_data(as_text=True)
    assert 'class="chips"' not in corpo


def test_o_x_do_chip_leva_para_a_url_sem_aquele_filtro(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/?centro=4561&natureza=COMBUSTIVEL").get_data(as_text=True)
    assert "natureza=COMBUSTIVEL" in corpo
    # O link de remover a natureza mantém o centro.
    assert "centro=4561" in corpo
