"""Importacao da planilha: previa, gravacao e idempotencia."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.importacao.servico import analisar, gravar
from app.models import Auditoria, CentroCusto, Despesa, Fornecedor, Importacao, Natureza, Usuario

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).parent.parent / "fixtures" / "cc4561_amostra.xlsx"


@pytest.fixture
def operador(db):
    usuario = Usuario(nome="Operador", email="op@ufcengenharia.com.br", perfil="operador")
    db.session.add(usuario)
    db.session.commit()
    return usuario


def previa(db):
    with FIXTURE.open("rb") as arquivo:
        return analisar(db.session, arquivo, arquivo_nome="cc4561.xlsx")


def importar(db, usuario=None):
    return gravar(db.session, previa(db), usuario=usuario)


# --- previa -----------------------------------------------------------------


def test_previa_nao_grava_nada(db):
    previa(db)
    assert db.session.scalar(select(func.count()).select_from(Despesa)) == 0


def test_previa_resume_o_arquivo(db):
    p = previa(db)
    assert len(p.linhas) == 127
    assert p.ignoradas == 39
    assert p.erros == []
    assert p.divergentes == 4
    assert p.total_baixado == Decimal("442949.60")
    assert p.total_original == Decimal("441947.21")


def test_previa_conta_o_que_e_novo(db):
    p = previa(db)
    assert len(p.novos_fornecedores) == 33
    assert len(p.novas_naturezas) == 7
    assert p.novos_centros == ["4561"]
    assert p.a_criar == 127
    assert p.a_atualizar == 0


def test_previa_de_reimportacao_conta_atualizacao(db):
    importar(db)
    p = previa(db)
    assert p.a_criar == 0
    assert p.a_atualizar == 127
    assert p.novos_fornecedores == []


def test_previa_avisa_que_o_arquivo_ja_entrou(db):
    importar(db)
    p = previa(db)
    assert p.ja_importado is not None
    assert p.ja_importado.arquivo == "cc4561.xlsx"


def test_previa_de_arquivo_inedito_nao_avisa(db):
    assert previa(db).ja_importado is None


# --- gravacao ---------------------------------------------------------------


def test_grava_os_127_lancamentos(db, operador):
    importacao = importar(db, operador)
    assert db.session.scalar(select(func.count()).select_from(Despesa)) == 127
    assert importacao.criados == 127
    assert importacao.atualizados == 0
    assert importacao.linhas_ignoradas == 39


def test_nenhum_subtotal_da_planilha_vira_registro(db):
    """Os 39 subtotais do Excel ficam de fora; todo total do sistema e SUM()."""
    importar(db)
    total = db.session.scalar(select(func.sum(Despesa.valor_baixado)))
    assert total == Decimal("442949.60")


def test_cria_o_dominio_a_partir_da_planilha(db):
    importar(db)
    assert db.session.scalar(select(func.count()).select_from(Fornecedor)) == 33
    assert db.session.scalar(select(func.count()).select_from(Natureza)) == 7
    assert db.session.scalar(select(func.count()).select_from(CentroCusto)) == 1


def test_despesa_aponta_para_o_lote_que_a_trouxe(db):
    importacao = importar(db)
    despesa = db.session.scalars(select(Despesa).where(Despesa.referencia == 136914)).one()
    assert despesa.importacao_id == importacao.id


def test_as_quatro_divergencias_chegam_ao_banco(db):
    importar(db)
    divergentes = db.session.scalars(select(Despesa).where(Despesa.divergente)).all()
    assert len(divergentes) == 4
    assert {d.referencia for d in divergentes} == {139049, 140748, 140538, 141402}


def test_historico_chega_normalizado(db):
    importar(db)
    historicos = db.session.scalars(select(Despesa.historico)).all()
    assert all("\n" not in texto for texto in historicos)


# --- idempotencia -----------------------------------------------------------


def test_reimportar_o_mesmo_arquivo_nao_duplica(db):
    importar(db)
    segunda = importar(db)
    assert db.session.scalar(select(func.count()).select_from(Despesa)) == 127
    assert segunda.criados == 0
    assert segunda.atualizados == 127


def test_reimportar_restaura_valor_alterado_a_mao(db):
    """A planilha e a fonte: reimportar traz o valor do ERP de volta."""
    importar(db)
    despesa = db.session.scalars(select(Despesa).where(Despesa.referencia == 136914)).one()
    despesa.valor_baixado = Decimal("1.00")
    db.session.commit()

    importar(db)
    db.session.refresh(despesa)
    assert despesa.valor_baixado == Decimal("693.00")


def test_reimportar_nao_duplica_fornecedor(db):
    importar(db)
    importar(db)
    assert db.session.scalar(select(func.count()).select_from(Fornecedor)) == 33


def test_cada_importacao_deixa_seu_registro(db, operador):
    importar(db, operador)
    importar(db, operador)
    lotes = db.session.scalars(select(Importacao)).all()
    assert len(lotes) == 2
    assert all(lote.usuario_id == operador.id for lote in lotes)
    assert lotes[0].sha256 == lotes[1].sha256


# --- auditoria --------------------------------------------------------------


def test_importacao_e_auditada_com_os_numeros(db, operador):
    importacao = importar(db, operador)
    entrada = db.session.scalars(
        select(Auditoria).where(Auditoria.acao == "importacao.gravar")
    ).one()
    assert entrada.usuario_id == operador.id
    assert entrada.alvo_id == importacao.id
    assert entrada.payload["criados"] == 127
    assert entrada.payload["ignoradas"] == 39
    assert entrada.payload["arquivo"] == "cc4561.xlsx"


# --- erros ------------------------------------------------------------------


def test_linhas_com_erro_ficam_de_fora_e_as_boas_entram(db, tmp_path):
    from openpyxl import Workbook

    caminho = tmp_path / "meia_boca.xlsx"
    livro = Workbook()
    aba = livro.active
    aba.append([None] * 10 + ["Total Geral", "Total Geral"])
    aba.append([
        "ANO_BAIXA", "MES_BAIXA", "DIA_BAIXA", "DATAEMISSAO", "REFERENCIA",
        "FORNECEDOR", "CR_REDUZIDO", "NATUREZA", "HISTORICO", "DOCUMENTO",
        "VALOR ORIGINAL", "VALOR BAIXADO",
    ])
    aba.append(["2026", "3", "9", 46059, 1, "BOA", "4561", "COMBUSTIVEL", "ok", "1", -10, -10])
    aba.append(["2026", "3", "9", 46059, None, "RUIM", "4561", "COMBUSTIVEL", "x", "2", -20, -20])
    livro.save(caminho)

    with caminho.open("rb") as arquivo:
        p = analisar(db.session, arquivo, arquivo_nome="meia_boca.xlsx")
    assert len(p.linhas) == 1
    assert len(p.erros) == 1

    gravar(db.session, p)
    assert db.session.scalar(select(func.count()).select_from(Despesa)) == 1


def test_arquivo_invalido_nao_deixa_rastro(db):
    from io import BytesIO

    with pytest.raises(ValueError, match="não parece uma planilha"):
        analisar(db.session, BytesIO(b"nada disso"), arquivo_nome="ruim.xlsx")
    assert db.session.scalar(select(func.count()).select_from(Importacao)) == 0


# --- planilha grande --------------------------------------------------------
#
# O IN gasta um parâmetro por referência, e o PostgreSQL para em 65535. Uma
# planilha grande estourava isso, sujava a sessão, e o erro saía como 500
# vários passos adiante (PendingRollbackError).


def planilha_de(quantidade: int, base: int):
    from io import BytesIO

    from openpyxl import Workbook

    livro = Workbook()
    aba = livro.active
    aba.append([])
    aba.append(
        ["ANO_BAIXA", "MES_BAIXA", "DIA_BAIXA", "DATAEMISSAO", "REFERENCIA",
         "FORNECEDOR", "CR_REDUZIDO", "NATUREZA", "HISTORICO", "DOCUMENTO",
         "VALOR ORIGINAL", "VALOR BAIXADO"]
    )
    for posicao in range(quantidade):
        aba.append(
            [2026, (posicao % 12) + 1, (posicao % 28) + 1, 46059, base + posicao,
             f"FORN {posicao % 20}", "4561", f"NAT {posicao % 5}",
             f"hist {posicao}", f"D{posicao}", -10.0, -10.0]
        )
    buffer = BytesIO()
    livro.save(buffer)
    buffer.seek(0)
    return buffer


def test_fatia_o_in_por_referencia(db):
    """Com mais referências que o teto de parâmetros, uma consulta só falharia."""
    from app.importacao.planilha import ler
    from app.importacao.servico import LOTE_DE_PARAMETROS, _chaves_existentes

    assert LOTE_DE_PARAMETROS < 65535
    # Não precisa de 65 mil linhas para exercitar o fatiamento: basta pedir mais
    # referências do que cabe num lote.
    linhas = ler(planilha_de(LOTE_DE_PARAMETROS * 2 + 7, 50_000_000)).linhas
    assert _chaves_existentes(db.session, linhas) == set()


def test_importa_mais_de_um_lote_de_uma_vez(db):
    from app.importacao.servico import LOTE_DE_PARAMETROS, analisar, gravar

    quantidade = LOTE_DE_PARAMETROS + 50
    previa = analisar(db.session, planilha_de(quantidade, 4_000_000), arquivo_nome="g.xlsx")
    importacao = gravar(db.session, previa, usuario=None)
    assert importacao.criados == quantidade


def test_reimportar_o_grande_atualiza_sem_duplicar(db):
    from app.importacao.servico import LOTE_DE_PARAMETROS, analisar, gravar

    quantidade = LOTE_DE_PARAMETROS + 50
    for _ in range(2):
        previa = analisar(db.session, planilha_de(quantidade, 6_000_000), arquivo_nome="g.xlsx")
        importacao = gravar(db.session, previa, usuario=None)

    assert importacao.criados == 0
    assert importacao.atualizados == quantidade


def test_progresso_e_chamado_por_lote(db):
    """Sem isso o comando fica minutos mudo numa planilha grande."""
    from app.importacao.servico import LOTE_DE_PARAMETROS, analisar, gravar

    quantidade = 100
    previa = analisar(db.session, planilha_de(quantidade, 7_000_000), arquivo_nome="p.xlsx")

    chamadas = []
    gravar(db.session, previa, usuario=None, progresso=lambda feitas, total: chamadas.append((feitas, total)))

    assert chamadas, "o callback não foi chamado"
    assert chamadas[-1] == (quantidade, quantidade)
    assert all(total == quantidade for _, total in chamadas)
    assert LOTE_DE_PARAMETROS  # sanidade do import
