"""Paginação.

Regressão de um bug real: os links diziam `?pagina=2`, mas o `db.paginate` lê
`page` da query string. Clicar em qualquer página devolvia sempre a primeira.
"""

from __future__ import annotations

import re

import pytest

pytestmark = pytest.mark.integration


def referencias_na_pagina(corpo: str) -> list[int]:
    """As referências que aparecem na tabela (coluna própria, 6 dígitos)."""
    return [int(n) for n in re.findall(r"<td>(1[34]\d{4})</td>", corpo)]


@pytest.fixture
def cliente(entrar, leitor, carregado):
    return entrar(leitor)


def test_primeira_pagina_traz_o_limite(cliente):
    corpo = cliente.get("/despesas").get_data(as_text=True)
    assert len(referencias_na_pagina(corpo)) == 50


def test_segunda_pagina_traz_outros_lancamentos(cliente):
    primeira = referencias_na_pagina(cliente.get("/despesas?pagina=1").get_data(as_text=True))
    segunda = referencias_na_pagina(cliente.get("/despesas?pagina=2").get_data(as_text=True))

    assert segunda, "a segunda página veio vazia"
    assert primeira != segunda, "a segunda página repetiu a primeira"
    assert not set(primeira) & set(segunda), "houve lançamento em duas páginas"


def test_ultima_pagina_traz_o_resto(cliente):
    # 127 lançamentos, 50 por página -> 3 páginas, a última com 27.
    corpo = cliente.get("/despesas?pagina=3").get_data(as_text=True)
    assert len(referencias_na_pagina(corpo)) == 27


def test_paginas_nao_se_sobrepoem_e_cobrem_tudo(cliente):
    vistas = []
    for numero in (1, 2, 3):
        corpo = cliente.get(f"/despesas?pagina={numero}").get_data(as_text=True)
        vistas.extend(referencias_na_pagina(corpo))
    assert len(vistas) == 127
    assert len(set(vistas)) == 127


def test_pagina_alem_do_fim_nao_quebra(cliente):
    resposta = cliente.get("/despesas?pagina=99")
    assert resposta.status_code == 200


def test_pagina_invalida_cai_na_primeira(cliente):
    """A URL é editável na barra de endereços."""
    corpo = cliente.get("/despesas?pagina=abc").get_data(as_text=True)
    assert len(referencias_na_pagina(corpo)) == 50


def test_paginacao_preserva_o_filtro(cliente):
    """Trocar de página não pode perder o recorte."""
    corpo = cliente.get("/despesas?natureza=SERVIÇOS ESPECIALIZADOS MEI&pagina=2").get_data(
        as_text=True
    )
    assert "78 lançamentos" in corpo
    assert len(referencias_na_pagina(corpo)) == 28  # 78 - 50


def test_links_de_paginacao_apontam_para_a_pagina_certa(cliente):
    corpo = cliente.get("/despesas").get_data(as_text=True)
    assert "pagina=2" in corpo
    assert "pagina=3" in corpo


def test_painel_mostra_so_os_ultimos_e_leva_para_a_lista(cliente):
    corpo = cliente.get("/").get_data(as_text=True)
    assert corpo.count("data-detalhe=") == 8
    assert "Ver todos os 127" in corpo


def test_lista_aceita_outro_tamanho_de_pagina(cliente):
    corpo = cliente.get("/despesas?por_pagina=25").get_data(as_text=True)
    assert len(referencias_na_pagina(corpo)) == 25
    assert "Mostrando 1–25 de 127" in re.sub(r"\s+", " ", corpo)


def test_tamanho_de_pagina_fora_da_lista_volta_ao_padrao(cliente):
    corpo = cliente.get("/despesas?por_pagina=5000").get_data(as_text=True)
    assert len(referencias_na_pagina(corpo)) == 50


def test_paginacao_da_auditoria(entrar, admin, db):
    from app.auditoria.servico import registrar

    for numero in range(140):
        registrar(
            db.session,
            acao="teste.paginacao",
            usuario=admin,
            alvo_tipo="despesa",
            alvo_id=numero,
        )
    db.session.commit()

    cliente = entrar(admin)
    primeira = cliente.get("/auditoria/?pagina=1").get_data(as_text=True)
    segunda = cliente.get("/auditoria/?pagina=2").get_data(as_text=True)
    # A celula da tabela, e nao a pagina toda: o combo de filtro tambem cita a acao.
    assert primeira.count('title="teste.paginacao"') == 60
    assert segunda.count('title="teste.paginacao"') == 60
    assert primeira != segunda
