"""API de leitura para o Controle Financeiro (/api/v1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text, update

from app.admin.manutencao import limpar
from app.models import Despesa, DespesaExcluida

pytestmark = pytest.mark.integration

TOKEN = "token-de-teste-do-financeiro"
CABECALHO = {"Authorization": f"Bearer {TOKEN}"}
ROTAS = [
    "/api/v1/despesas",
    "/api/v1/despesas/exclusoes",
    "/api/v1/despesas/ids",
    "/api/v1/centros_custo",
    "/api/v1/fornecedores",
    "/api/v1/naturezas",
    "/api/v1/status",
]


@pytest.fixture
def api(app, client):
    app.config["SYNC_API_TOKEN"] = TOKEN
    yield client
    app.config["SYNC_API_TOKEN"] = ""


# --- autenticação -----------------------------------------------------------


@pytest.mark.parametrize("rota", ROTAS)
def test_recusa_sem_token(api, rota):
    assert api.get(rota).status_code == 401


@pytest.mark.parametrize("rota", ROTAS)
def test_recusa_token_errado(api, rota):
    assert api.get(rota, headers={"Authorization": "Bearer errado"}).status_code == 401


def test_sem_token_configurado_a_api_fica_desligada(client):
    assert client.get("/api/v1/despesas", headers=CABECALHO).status_code == 503


def test_sessao_de_usuario_nao_substitui_o_token(app, entrar, admin):
    app.config["SYNC_API_TOKEN"] = TOKEN
    try:
        assert entrar(admin).get("/api/v1/despesas").status_code == 401
    finally:
        app.config["SYNC_API_TOKEN"] = ""


# --- listagens --------------------------------------------------------------


def test_despesas_trazem_valores_como_texto(api, carregado):
    corpo = api.get("/api/v1/despesas?limit=5", headers=CABECALHO).get_json()
    assert corpo["count"] == 5
    assert corpo["has_more"] is True
    primeira = corpo["despesas"][0]
    assert isinstance(primeira["valor_baixado"], str)
    assert {"centro_custo_id", "natureza_id", "fornecedor_id", "data_baixa"} <= primeira.keys()
    assert corpo["watermark"] == corpo["despesas"][-1]["atualizado_em"]


def test_paginacao_cobre_tudo_sem_repetir(api, carregado, db):
    total = db.session.query(Despesa).count()
    vistos, offset = [], 0
    while True:
        corpo = api.get(f"/api/v1/despesas?limit=40&offset={offset}", headers=CABECALHO).get_json()
        vistos += [d["id"] for d in corpo["despesas"]]
        if not corpo["has_more"]:
            break
        offset += 40
    assert len(vistos) == len(set(vistos)) == total


def test_incremental_so_traz_o_que_mudou(api, carregado, db):
    antes = datetime.now(UTC) - timedelta(days=2)
    db.session.execute(update(Despesa).values(atualizado_em=antes))
    alvo = db.session.scalars(select(Despesa)).first()
    alvo.historico = "alterada"
    db.session.commit()

    marca = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    corpo = api.get(
        "/api/v1/despesas", query_string={"updated_since": marca}, headers=CABECALHO
    ).get_json()
    assert [d["id"] for d in corpo["despesas"]] == [alvo.id]


def test_dominios_e_centro_com_codigo(api, carregado):
    centros = api.get("/api/v1/centros_custo", headers=CABECALHO).get_json()["centros_custo"]
    assert centros and "codigo" in centros[0]
    assert api.get("/api/v1/naturezas", headers=CABECALHO).get_json()["naturezas"]
    assert api.get("/api/v1/fornecedores", headers=CABECALHO).get_json()["fornecedores"]


def test_status_bate_com_a_contagem(api, carregado, db):
    corpo = api.get("/api/v1/status", headers=CABECALHO).get_json()
    assert corpo["despesas"]["count"] == db.session.query(Despesa).count()
    assert isinstance(corpo["despesas"]["sum_valor_baixado"], str)


# --- exclusões: a trigger pega qualquer caminho -----------------------------


def _ids_excluidos(api):
    corpo = api.get("/api/v1/despesas/exclusoes", headers=CABECALHO).get_json()
    return {x["id"] for x in corpo["exclusoes"]}


def test_exclusao_pela_tela_aparece(api, entrar, operador, carregado, db):
    despesa = db.session.scalars(select(Despesa)).first()
    entrar(operador).post(f"/despesas/{despesa.id}/excluir")
    assert despesa.id in _ids_excluidos(api)


def test_limpeza_em_massa_aparece(api, carregado, db):
    ids = set(db.session.scalars(select(Despesa.id)).all())
    limpar(db.session, "despesas")
    db.session.commit()
    assert _ids_excluidos(api) == ids


def test_delete_em_sql_cru_aparece(api, carregado, db):
    despesa_id = db.session.scalars(select(Despesa.id)).first()
    db.session.execute(text("DELETE FROM tb_despesas WHERE id = :i"), {"i": despesa_id})
    db.session.commit()
    assert despesa_id in _ids_excluidos(api)
    assert db.session.get(DespesaExcluida, despesa_id) is not None


def test_ids_listam_so_o_que_existe(api, carregado, db):
    despesa_id = db.session.scalars(select(Despesa.id)).first()
    db.session.execute(text("DELETE FROM tb_despesas WHERE id = :i"), {"i": despesa_id})
    db.session.commit()
    ids = api.get("/api/v1/despesas/ids", headers=CABECALHO).get_json()["ids"]
    assert despesa_id not in ids
    assert len(ids) == db.session.query(Despesa).count()
