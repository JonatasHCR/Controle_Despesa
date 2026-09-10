"""Modelos e as regras que vivem no banco.

O teste central desta suite e o da divergencia: ela e derivada, nunca gravada.
Guardar a flag exigiria recalcular em todo UPDATE, e o dia em que alguem
esquecesse, o filtro passaria a mentir sem nenhum sintoma. Aqui se prova que a
mesma definicao vale em Python e em SQL, e que nao existe passo de recalculo.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import (
    Auditoria,
    CentroCusto,
    Despesa,
    Fornecedor,
    Natureza,
    Usuario,
)

pytestmark = pytest.mark.integration


def criar_despesa(db, *, referencia=1, original="100.00", baixado="100.00", **extra):
    despesa = Despesa(
        referencia=referencia,
        data_baixa=extra.pop("data_baixa", date(2026, 3, 9)),
        data_emissao=extra.pop("data_emissao", date(2026, 2, 6)),
        centro_custo=CentroCusto.obter_ou_criar(db.session, "4561"),
        fornecedor=Fornecedor.obter_ou_criar(db.session, extra.pop("fornecedor", "FORNECEDOR A")),
        natureza=Natureza.obter_ou_criar(db.session, extra.pop("natureza", "COMBUSTIVEL")),
        historico=extra.pop("historico", "abastecimento"),
        documento=extra.pop("documento", "0001"),
        valor_original=Decimal(original),
        valor_baixado=Decimal(baixado),
        **extra,
    )
    db.session.add(despesa)
    db.session.commit()
    return despesa


# --- divergencia: derivada, nunca armazenada --------------------------------


def test_divergente_e_falso_quando_os_valores_batem(db):
    despesa = criar_despesa(db, original="100.00", baixado="100.00")
    assert despesa.divergente is False
    assert despesa.diferenca == Decimal("0.00")


def test_divergente_e_verdadeiro_quando_os_valores_diferem(db):
    despesa = criar_despesa(db, original="6250.74", baixado="6331.26")
    assert despesa.divergente is True
    assert despesa.diferenca == Decimal("80.52")


def test_divergente_funciona_como_filtro_em_sql(db):
    """A mesma definicao no WHERE."""
    criar_despesa(db, referencia=1, original="100.00", baixado="100.00")
    criar_despesa(db, referencia=2, original="100.00", baixado="150.00")
    criar_despesa(db, referencia=3, original="200.00", baixado="200.00")

    divergentes = db.session.scalars(select(Despesa).where(Despesa.divergente)).all()
    assert [d.referencia for d in divergentes] == [2]

    iguais = db.session.scalars(select(Despesa).where(~Despesa.divergente)).all()
    assert sorted(d.referencia for d in iguais) == [1, 3]


def test_editar_o_valor_muda_o_filtro_na_hora(db):
    """Mudou o valor, mudou o filtro: nao existe passo de recalculo."""
    despesa = criar_despesa(db, referencia=7, original="100.00", baixado="100.00")
    assert db.session.scalars(select(Despesa).where(Despesa.divergente)).all() == []

    despesa.valor_baixado = Decimal("120.00")
    db.session.commit()

    achadas = db.session.scalars(select(Despesa).where(Despesa.divergente)).all()
    assert [d.referencia for d in achadas] == [7]

    despesa.valor_baixado = Decimal("100.00")
    db.session.commit()
    assert db.session.scalars(select(Despesa).where(Despesa.divergente)).all() == []


def test_null_de_um_lado_nao_some_do_filtro(db):
    """`<>` com NULL devolve NULL e a linha sumiria calada."""
    criar_despesa(db, referencia=9, original="100.00", baixado="100.00")
    despesa = db.session.scalars(select(Despesa)).one()
    despesa.valor_original = None
    db.session.commit()

    achadas = db.session.scalars(select(Despesa).where(Despesa.divergente)).all()
    assert [d.referencia for d in achadas] == [9]


def test_divergente_nao_e_coluna_da_tabela(db):
    """Se virar coluna um dia, este teste avisa antes de a inconsistencia aparecer em producao."""
    colunas = {coluna.name for coluna in Despesa.__table__.columns}
    assert "divergente" not in colunas
    assert "diferenca" not in colunas


# --- chave natural e integridade -------------------------------------------


def test_referencia_e_unica(db):
    criar_despesa(db, referencia=100)
    with pytest.raises(IntegrityError):
        criar_despesa(db, referencia=100, fornecedor="OUTRO")


def test_valor_negativo_e_recusado(db):
    """Tudo e gravado positivo; negativo aqui so pode ser bug."""
    with pytest.raises(IntegrityError):
        criar_despesa(db, referencia=101, original="-10.00", baixado="-10.00")


def test_despesa_lancada_a_mao_nao_tem_importacao(db):
    despesa = criar_despesa(db, referencia=102)
    assert despesa.importacao_id is None


# --- tabelas de dominio -----------------------------------------------------


def test_obter_ou_criar_nao_duplica(db):
    primeiro = Fornecedor.obter_ou_criar(db.session, "LOCALIZA RENT A CAR S/A")
    db.session.commit()
    segundo = Fornecedor.obter_ou_criar(db.session, "LOCALIZA RENT A CAR S/A")
    db.session.commit()
    assert primeiro.id == segundo.id
    assert db.session.scalars(select(Fornecedor)).all() == [primeiro]


def test_obter_ou_criar_normaliza_espacos_e_caixa(db):
    """' localiza ' e 'LOCALIZA' sao o mesmo fornecedor."""
    primeiro = Fornecedor.obter_ou_criar(db.session, "LOCALIZA RENT A CAR S/A")
    db.session.commit()
    segundo = Fornecedor.obter_ou_criar(db.session, "  localiza rent a car s/a  ")
    db.session.commit()
    assert primeiro.id == segundo.id
    assert primeiro.nome == "LOCALIZA RENT A CAR S/A"  # a primeira grafia vence


def test_centro_de_custo_guarda_codigo_e_nome(db):
    centro = CentroCusto.obter_ou_criar(db.session, "4561", nome="OBRA MORAR MELHOR")
    db.session.commit()
    assert centro.codigo == "4561"
    assert centro.nome == "OBRA MORAR MELHOR"


def test_centro_sem_nome_usa_o_codigo(db):
    centro = CentroCusto.obter_ou_criar(db.session, "4561")
    db.session.commit()
    assert centro.nome == "4561"


# --- usuarios e perfis ------------------------------------------------------


@pytest.mark.parametrize(
    "perfil,pode_ler,pode_escrever,pode_administrar",
    [
        ("leitor", True, False, False),
        ("operador", True, True, False),
        ("admin", True, True, True),
    ],
)
def test_o_que_cada_perfil_pode(db, perfil, pode_ler, pode_escrever, pode_administrar):
    usuario = Usuario(nome="Fulano", email=f"{perfil}@x.com", perfil=perfil)
    db.session.add(usuario)
    db.session.commit()
    assert usuario.pode_ler is pode_ler
    assert usuario.pode_escrever is pode_escrever
    assert usuario.pode_administrar is pode_administrar


def test_perfil_desconhecido_e_recusado_pelo_banco(db):
    db.session.add(Usuario(nome="X", email="x@x.com", perfil="superusuario"))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_usuario_novo_nasce_como_leitor(db):
    """Menor privilegio: quem entra pela primeira vez consulta, e alguem promove."""
    usuario = Usuario(nome="Novo", email="novo@x.com")
    db.session.add(usuario)
    db.session.commit()
    assert usuario.perfil == "leitor"
    assert usuario.ativo is True


def test_email_e_unico(db):
    db.session.add(Usuario(nome="A", email="mesmo@x.com"))
    db.session.commit()
    db.session.add(Usuario(nome="B", email="mesmo@x.com"))
    with pytest.raises(IntegrityError):
        db.session.commit()


# --- auditoria --------------------------------------------------------------


def test_auditoria_sobrevive_a_remocao_do_usuario(db):
    """ON DELETE SET NULL: o registro do que aconteceu nao pode sumir junto com quem fez."""
    usuario = Usuario(nome="Fulano", email="f@x.com", perfil="operador")
    db.session.add(usuario)
    db.session.commit()

    db.session.add(
        Auditoria(
            acao="despesa.criar",
            usuario_id=usuario.id,
            alvo_tipo="despesa",
            alvo_id=1,
            payload={"referencia": 136914},
        )
    )
    db.session.commit()

    db.session.delete(usuario)
    db.session.commit()

    entrada = db.session.scalars(select(Auditoria)).one()
    assert entrada.usuario_id is None
    assert entrada.acao == "despesa.criar"
    assert entrada.payload == {"referencia": 136914}
