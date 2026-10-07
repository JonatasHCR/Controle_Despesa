"""Painel com Chart.js, gaveta do lançamento, relatório com detalhe e exportação."""

from __future__ import annotations

import json
import re

import pytest
from sqlalchemy import select

pytestmark = pytest.mark.integration


@pytest.fixture
def cliente(entrar, leitor, carregado):
    return entrar(leitor)


def _dados_dos_graficos(corpo: str) -> dict:
    bloco = re.search(r'<script type="application/json" id="dados-graficos">(.*?)</script>', corpo, re.S)
    return json.loads(bloco.group(1))


def test_graficos_recebem_os_totais_do_servidor(cliente):
    dados = _dados_dos_graficos(cliente.get("/").get_data(as_text=True))
    assert round(sum(linha["total"] for linha in dados["natureza"]), 2) == 442949.60
    assert all({"inicio", "fim", "rotulo"} <= set(ponto) for ponto in dados["tempo"])


def test_mes_filtrado_vem_marcado_no_grafico(cliente):
    dados = _dados_dos_graficos(cliente.get("/").get_data(as_text=True))
    ponto = dados["tempo"][0]
    filtrado = cliente.get(f"/?inicio={ponto['inicio']}&fim={ponto['fim']}").get_data(as_text=True)
    marcados = [p for p in _dados_dos_graficos(filtrado)["tempo"] if p["escolhido"]]
    assert [p["inicio"] for p in marcados] == [ponto["inicio"]]


def test_ranking_de_centro_liga_e_desliga_o_filtro(cliente):
    corpo = cliente.get("/").get_data(as_text=True)
    assert "Por centro de custo" in corpo
    assert "centro=4561" in corpo

    filtrado = cliente.get("/?centro=4561").get_data(as_text=True)
    assert 'aria-current="true"' in filtrado


def test_atalhos_de_periodo_partem_do_ultimo_lancamento(cliente):
    corpo = cliente.get("/despesas").get_data(as_text=True)
    assert 'class="atalho"' in corpo
    assert "Últimos 3 meses" in corpo


def test_gaveta_mostra_o_lancamento_e_o_historico(entrar, operador, carregado, db):
    from app.models import Despesa

    despesa = db.session.scalars(select(Despesa).where(Despesa.referencia == 136914)).first()
    cliente = entrar(operador)
    corpo = cliente.get(f"/despesas/{despesa.id}").get_data(as_text=True)
    assert "136914" in corpo
    assert "Sem alterações registradas" in corpo
    assert "<html" not in corpo
    assert "Editar" in corpo


def test_gaveta_de_lancamento_inexistente_e_404(cliente):
    assert cliente.get("/despesas/999999").status_code == 404


def test_relatorio_agrupa_por_natureza_sem_pedir(cliente):
    corpo = cliente.get("/relatorios/").get_data(as_text=True)
    assert "SERVIÇOS ESPECIALIZADOS MEI" in corpo
    assert "agrupar=natureza" in corpo


def test_relatorio_detalha_cada_grupo(cliente):
    corpo = cliente.get("/relatorios/?agrupar=natureza&detalhar=fornecedor").get_data(as_text=True)
    assert "data-de-grupo=" in corpo
    assert "do grupo" in corpo


def test_relatorio_mostra_so_os_maiores(cliente):
    corpo = cliente.get("/relatorios/?agrupar=fornecedor&mostrar=10").get_data(as_text=True)
    assert corpo.count('class="subtotal') <= 10


def test_pdf_grande_demais_responde_a_janela_com_a_mensagem(cliente, monkeypatch):
    from app.relatorios import pdf

    monkeypatch.setattr(pdf, "TETO_DE_LINHAS", 5)
    resposta = cliente.get("/relatorios/pdf", headers={"X-Exportar": "1"})
    assert resposta.status_code == 422
    assert "limite de 5" in resposta.get_json()["erro"]
