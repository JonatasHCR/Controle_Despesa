"""Filtros de domínio aceitam termo parcial, não só o nome inteiro.

Os campos viraram caixas de busca (input + datalist). Quem escolhe da lista
manda o nome completo; quem digita um pedaço e aperta Enter manda o pedaço — e
não pode receber "nenhum resultado" por isso.

A resolução acontece aqui, na camada da query string, e não no motor de filtro:
o motor continua comparando por igualdade, que é o que garante que
"SERVIÇOS DE ORÇAMENTO" nunca arraste "SERVIÇOS DIVERSOS".
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from werkzeug.datastructures import MultiDict

from app.despesas.consulta import filtro_da_query
from app.despesas.filtros import aplicar
from app.models import Despesa

pytestmark = pytest.mark.integration


def filtrar(db, **parametros):
    args = MultiDict(parametros)
    filtro = filtro_da_query(args, sessao=db.session)
    return db.session.scalars(aplicar(select(Despesa), filtro)).all()


# --- natureza ---------------------------------------------------------------


def test_nome_completo_da_natureza(carregado):
    assert len(filtrar(carregado, natureza="COMBUSTIVEL")) == 5


def test_pedaco_do_nome_da_natureza(carregado):
    """Digitar 'MEI' precisa achar 'SERVIÇOS ESPECIALIZADOS MEI'."""
    assert len(filtrar(carregado, natureza="MEI")) == 78


def test_pedaco_que_pega_varias_naturezas(carregado):
    """'SERVIÇOS' aparece em quatro naturezas; as quatro entram."""
    achadas = filtrar(carregado, natureza="SERVIÇOS")
    assert len({d.natureza.nome for d in achadas}) == 4
    assert len(achadas) == 78 + 30 + 4 + 1


def test_busca_de_natureza_ignora_caixa_e_espacos(carregado):
    assert len(filtrar(carregado, natureza="  combustivel  ")) == 5


def test_nome_completo_nao_arrasta_o_parecido(carregado):
    """A garantia que existia antes continua valendo para quem escolhe da lista."""
    achadas = filtrar(carregado, natureza="SERVIÇOS DE ORÇAMENTO")
    assert len(achadas) == 1


def test_natureza_inexistente_nao_traz_nada(carregado):
    assert filtrar(carregado, natureza="NATUREZA QUE NAO EXISTE") == []


# --- fornecedor -------------------------------------------------------------


def test_pedaco_do_nome_do_fornecedor(carregado):
    achadas = filtrar(carregado, fornecedor="LOCALIZA")
    assert achadas
    assert all("LOCALIZA" in d.fornecedor.nome for d in achadas)


def test_fornecedor_pelo_primeiro_nome(carregado):
    achadas = filtrar(carregado, fornecedor="isabela")
    assert achadas
    assert all("ISABELA" in d.fornecedor.nome for d in achadas)


def test_fornecedor_completo(carregado):
    achadas = filtrar(carregado, fornecedor="JOCKEY AUTO POSTO LTDA")
    assert len(achadas) == 1


# --- centro de custo --------------------------------------------------------


def test_centro_pelo_codigo(carregado):
    assert len(filtrar(carregado, centro="4561")) == 127


def test_centro_por_pedaco_do_codigo(carregado):
    assert len(filtrar(carregado, centro="456")) == 127


def test_centro_inexistente(carregado):
    assert filtrar(carregado, centro="9999") == []


# --- combinações ------------------------------------------------------------


def test_termos_parciais_se_somam(carregado):
    achadas = filtrar(carregado, natureza="MEI", fornecedor="ISABELA")
    assert achadas
    assert all(d.natureza.nome == "SERVIÇOS ESPECIALIZADOS MEI" for d in achadas)
    assert all("ISABELA" in d.fornecedor.nome for d in achadas)


def test_curinga_do_like_e_literal_tambem_aqui(carregado):
    """Sem escapar, '%' traria a base inteira."""
    assert filtrar(carregado, natureza="%") == []


def test_sem_sessao_o_filtro_continua_funcionando(carregado):
    """A resolução é opcional: sem sessão, vale o nome exato."""
    args = MultiDict({"natureza": "COMBUSTIVEL"})
    filtro = filtro_da_query(args)
    achadas = carregado.session.scalars(aplicar(select(Despesa), filtro)).all()
    assert len(achadas) == 5


# --- pela tela --------------------------------------------------------------


def test_busca_parcial_funciona_pela_url(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/despesas?natureza=MEI").get_data(as_text=True)
    assert "78 lançamento" in corpo


def test_campos_de_dominio_sao_caixas_de_busca(entrar, leitor, carregado):
    """input + datalist: pesquisável, sem depender de biblioteca."""
    corpo = entrar(leitor).get("/despesas").get_data(as_text=True)
    for campo in ("natureza", "fornecedor", "centro"):
        assert f'list="opcoes-{campo}"' in corpo
        assert f'id="opcoes-{campo}"' in corpo


def test_datalist_traz_as_opcoes_do_banco(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/despesas").get_data(as_text=True)
    assert "LOCALIZA RENT A CAR S/A" in corpo
    assert "SERVIÇOS ESPECIALIZADOS MEI" in corpo
