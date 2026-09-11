"""As rotas: quem alcanca o que, e o que a tela devolve."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import Auditoria, Despesa

pytestmark = pytest.mark.integration


# --- porta de entrada -------------------------------------------------------


@pytest.mark.parametrize(
    "caminho",
    ["/", "/despesas", "/relatorios/", "/importacao/", "/auditoria/", "/administracao/"],
)
def test_deslogado_e_mandado_para_o_login(client, caminho):
    resposta = client.get(caminho)
    assert resposta.status_code == 302
    assert "/auth/login" in resposta.headers["Location"]


def test_health_nao_exige_login(client):
    assert client.get("/health").status_code == 200


def test_pedido_htmx_deslogado_recebe_hx_redirect(client):
    """Um redirect comum seria seguido pelo fetch e a tela de login acabaria
    dentro de um fragmento da pagina."""
    resposta = client.get("/despesas", headers={"HX-Request": "true"})
    assert "HX-Redirect" in resposta.headers


def test_usuario_desativado_perde_o_acesso(client, entrar, leitor, db):
    leitor.ativo = False
    db.session.commit()
    resposta = entrar(leitor).get("/")
    assert resposta.status_code == 302


# --- o que cada perfil alcanca ---------------------------------------------


@pytest.mark.parametrize("caminho", ["/", "/despesas", "/relatorios/"])
def test_leitor_consulta_e_gera_relatorio(entrar, leitor, carregado, caminho):
    assert entrar(leitor).get(caminho).status_code == 200


@pytest.mark.parametrize(
    "caminho", ["/importacao/", "/despesas/nova", "/auditoria/", "/administracao/"]
)
def test_leitor_nao_escreve_nem_administra(entrar, leitor, caminho):
    assert entrar(leitor).get(caminho).status_code == 403


@pytest.mark.parametrize("caminho", ["/importacao/", "/despesas/nova"])
def test_operador_importa_e_lanca(entrar, operador, caminho):
    assert entrar(operador).get(caminho).status_code == 200


@pytest.mark.parametrize("caminho", ["/auditoria/", "/administracao/"])
def test_operador_nao_administra(entrar, operador, caminho):
    assert entrar(operador).get(caminho).status_code == 403


@pytest.mark.parametrize("caminho", ["/auditoria/", "/administracao/", "/importacao/"])
def test_admin_alcanca_tudo(entrar, admin, caminho):
    assert entrar(admin).get(caminho).status_code == 200


# --- painel -----------------------------------------------------------------


def test_painel_traz_os_indicadores_e_os_dois_graficos(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/").get_data(as_text=True)
    assert "R$ 442.949,60" in corpo
    assert "Total baixado" in corpo
    assert corpo.count("<svg") == 2
    assert "Despesa por natureza" in corpo
    assert "Despesa por mês" in corpo


def test_indicadores_seguem_o_filtro(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/?natureza=COMBUSTIVEL").get_data(as_text=True)
    assert "R$ 442.949,60" not in corpo


def test_painel_sem_dados_nao_quebra(entrar, leitor):
    corpo = entrar(leitor).get("/").get_data(as_text=True)
    assert "Sem dados para o filtro atual" in corpo


def test_painel_destaca_as_divergencias_em_bloco_proprio(entrar, leitor, carregado):
    """A divergência é o que pede ação: não é um número entre outros."""
    corpo = entrar(leitor).get("/").get_data(as_text=True)
    assert "bloco-divergencia" in corpo
    assert "lançamentos divergentes" in corpo
    assert "diferença acumulada" in corpo


def test_painel_soma_a_diferenca_das_divergencias(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/").get_data(as_text=True)
    assert "+1.002,39" in corpo


def test_painel_cita_o_fornecedor_quando_todas_sao_dele(entrar, leitor, carregado):
    """As quatro divergências do arquivo são da Localiza."""
    corpo = entrar(leitor).get("/").get_data(as_text=True)
    assert "LOCALIZA RENT A CAR S/A" in corpo


def test_painel_sem_divergencia_diz_que_esta_limpo(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/?natureza=COMBUSTIVEL").get_data(as_text=True)
    assert "Sem divergências" in corpo
    assert "bloco-divergencia limpo" in corpo


def test_botao_leva_para_as_divergencias_preservando_o_filtro(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/?centro=4561").get_data(as_text=True)
    assert "divergentes=1" in corpo
    assert "centro=4561" in corpo


# --- lista e filtros pela URL ----------------------------------------------


def test_lista_pagina_os_lancamentos(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/despesas").get_data(as_text=True)
    assert "127 lançamentos" in corpo


def test_filtro_pela_query_string(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/despesas?natureza=COMBUSTIVEL").get_data(as_text=True)
    assert "5 lançamentos" in corpo


def test_htmx_devolve_so_o_fragmento(entrar, leitor, carregado):
    resposta = entrar(leitor).get("/despesas", headers={"HX-Request": "true"})
    corpo = resposta.get_data(as_text=True)
    assert "<html" not in corpo
    assert 'id="resultado"' in corpo


def test_agrupamento_mostra_subtotais(entrar, leitor, carregado):
    corpo = entrar(leitor).get("/despesas?agrupar=natureza").get_data(as_text=True)
    assert "Total geral" in corpo
    assert "SERVIÇOS ESPECIALIZADOS MEI" in corpo


def test_query_string_invalida_nao_derruba_a_tela(entrar, leitor, carregado):
    """A URL e editavel na barra de enderecos."""
    resposta = entrar(leitor).get("/despesas?inicio=nao-e-data&ordem=;DROP&valor_minimo=abc")
    assert resposta.status_code == 200


# --- CRUD -------------------------------------------------------------------


def formulario(**extra):
    dados = {
        "referencia": "999001",
        "data_baixa": "2026-05-10",
        "data_emissao": "2026-05-01",
        "centro_custo": "4561",
        "fornecedor": "FORNECEDOR DE TESTE",
        "natureza": "COMBUSTIVEL",
        "historico": "abastecimento",
        "documento": "0001",
        "valor_baixado": "1234,56",
    }
    dados.update(extra)
    return dados


def test_operador_cria_despesa(entrar, operador, db):
    resposta = entrar(operador).post("/despesas/nova", data=formulario(), follow_redirects=True)
    assert resposta.status_code == 200
    despesa = db.session.scalars(select(Despesa)).one()
    assert despesa.referencia == 999001
    assert despesa.valor_baixado == Decimal("1234.56")


def test_valor_original_em_branco_copia_o_baixado(entrar, operador, db):
    entrar(operador).post("/despesas/nova", data=formulario(), follow_redirects=True)
    despesa = db.session.scalars(select(Despesa)).one()
    assert despesa.valor_original == despesa.valor_baixado
    assert despesa.divergente is False


def test_valores_diferentes_marcam_divergencia(entrar, operador, db):
    entrar(operador).post(
        "/despesas/nova",
        data=formulario(valor_original="1000,00", valor_baixado="1100,00"),
        follow_redirects=True,
    )
    despesa = db.session.scalars(select(Despesa)).one()
    assert despesa.divergente is True


def test_referencia_repetida_com_fornecedor_diferente_passa(entrar, operador, db, carregado):
    """Mesma referência, outro fornecedor: é outro lançamento."""
    resposta = entrar(operador).post(
        "/despesas/nova",
        data=formulario(referencia="136914", fornecedor="FORNECEDOR INEDITO"),
        follow_redirects=True,
    )
    assert resposta.status_code == 200
    assert (
        db.session.scalars(
            select(Despesa).where(Despesa.referencia == 136914)
        ).all().__len__()
        == 2
    )


def test_lancamento_identico_e_recusado(entrar, operador, db, carregado):
    existente = db.session.scalars(
        select(Despesa).where(Despesa.referencia == 136914)
    ).one()
    resposta = entrar(operador).post(
        "/despesas/nova",
        data=formulario(
            referencia="136914",
            data_baixa=existente.data_baixa.isoformat(),
            fornecedor=existente.fornecedor.nome,
            natureza=existente.natureza.nome,
            centro_custo=existente.centro_custo.codigo,
            documento=existente.documento,
            historico=existente.historico,
        ),
    )
    assert resposta.status_code == 400
    assert "Já existe" in resposta.get_data(as_text=True)


def test_mesmo_lancamento_em_outra_data_de_baixa_passa(entrar, operador, db, carregado):
    existente = db.session.scalars(
        select(Despesa).where(Despesa.referencia == 136914)
    ).one()
    resposta = entrar(operador).post(
        "/despesas/nova",
        data=formulario(
            referencia="136914",
            data_baixa="2026-12-25",
            fornecedor=existente.fornecedor.nome,
            natureza=existente.natureza.nome,
            centro_custo=existente.centro_custo.codigo,
            documento=existente.documento,
            historico=existente.historico,
        ),
        follow_redirects=True,
    )
    assert resposta.status_code == 200
    assert len(db.session.scalars(select(Despesa).where(Despesa.referencia == 136914)).all()) == 2


def test_campo_obrigatorio_faltando_volta_com_mensagem(entrar, operador):
    resposta = entrar(operador).post("/despesas/nova", data=formulario(data_baixa=""))
    assert resposta.status_code == 400
    assert "data de baixa" in resposta.get_data(as_text=True)


def test_criar_despesa_e_auditado(entrar, operador, db):
    entrar(operador).post("/despesas/nova", data=formulario(), follow_redirects=True)
    entrada = db.session.scalars(select(Auditoria).where(Auditoria.acao == "despesa.criar")).one()
    assert entrada.usuario_id == operador.id
    assert entrada.payload["referencia"] == 999001


def test_editar_guarda_o_antes_e_o_depois(entrar, operador, db, carregado):
    despesa = db.session.scalars(select(Despesa).where(Despesa.referencia == 136914)).one()
    entrar(operador).post(
        f"/despesas/{despesa.id}/editar",
        data=formulario(referencia="136914", valor_baixado="700,00"),
        follow_redirects=True,
    )
    entrada = db.session.scalars(select(Auditoria).where(Auditoria.acao == "despesa.editar")).one()
    assert entrada.payload["antes"]["valor_baixado"] == "693.00"
    assert entrada.payload["depois"]["valor_baixado"] == "700.00"


def test_excluir_remove_e_audita(entrar, operador, db, carregado):
    despesa = db.session.scalars(select(Despesa).where(Despesa.referencia == 136914)).one()
    identificador = despesa.id
    entrar(operador).post(f"/despesas/{identificador}/excluir", follow_redirects=True)
    assert db.session.get(Despesa, identificador) is None
    assert db.session.scalars(
        select(Auditoria).where(Auditoria.acao == "despesa.excluir")
    ).one() is not None


def test_leitor_nao_exclui(entrar, leitor, db, carregado):
    despesa = db.session.scalars(select(Despesa).where(Despesa.referencia == 136914)).one()
    resposta = entrar(leitor).post(f"/despesas/{despesa.id}/excluir")
    assert resposta.status_code == 403
    assert db.session.scalar(select(func.count()).select_from(Despesa)) == 127


def test_despesa_inexistente_da_404(entrar, operador):
    assert entrar(operador).get("/despesas/999999/editar").status_code == 404


# --- importacao pela tela ---------------------------------------------------


def test_fluxo_de_importacao_ponta_a_ponta(entrar, operador, db):
    from io import BytesIO
    from pathlib import Path

    fixture = Path(__file__).parent.parent / "fixtures" / "cc4561_amostra.xlsx"
    cliente = entrar(operador)

    previa = cliente.post(
        "/importacao/previa",
        data={"planilha": (BytesIO(fixture.read_bytes()), "cc4561.xlsx")},
        content_type="multipart/form-data",
    )
    corpo = previa.get_data(as_text=True)
    assert previa.status_code == 200
    assert "127" in corpo
    assert "39" in corpo  # os subtotais ignorados
    assert db.session.scalar(select(func.count()).select_from(Despesa)) == 0  # previa nao grava

    confirmacao = cliente.post("/importacao/confirmar", follow_redirects=True)
    assert confirmacao.status_code == 200
    assert db.session.scalar(select(func.count()).select_from(Despesa)) == 127


def test_arquivo_que_nao_e_xlsx_e_recusado(entrar, operador):
    from io import BytesIO

    resposta = entrar(operador).post(
        "/importacao/previa",
        data={"planilha": (BytesIO(b"nada"), "planilha.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert ".xlsx" in resposta.get_data(as_text=True)


def test_xlsx_corrompido_avisa_sem_quebrar(entrar, operador):
    from io import BytesIO

    resposta = entrar(operador).post(
        "/importacao/previa",
        data={"planilha": (BytesIO(b"isto nao e um zip"), "ruim.xlsx")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resposta.status_code == 200
    assert "não parece uma planilha" in resposta.get_data(as_text=True)


def test_confirmar_sem_previa_pede_o_arquivo_de_novo(entrar, operador):
    resposta = entrar(operador).post("/importacao/confirmar", follow_redirects=True)
    assert "prévia expirou" in resposta.get_data(as_text=True)


def test_leitor_nao_importa(entrar, leitor):
    from io import BytesIO

    resposta = entrar(leitor).post(
        "/importacao/previa",
        data={"planilha": (BytesIO(b"x"), "a.xlsx")},
        content_type="multipart/form-data",
    )
    assert resposta.status_code == 403
