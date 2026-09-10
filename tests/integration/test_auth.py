"""Resolucao de usuario a partir do token e guardas de rota."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.auth.oidc import SemAcesso, resolver_usuario
from app.models import Usuario

pytestmark = pytest.mark.integration

GRUPO = "/apps/controle-despesa"
MESTRE = "admin@ufcengenharia.com.br"


def claims(**extra):
    base = {
        "sub": "sub-123",
        "email": "fulano@ufcengenharia.com.br",
        "name": "Fulano de Tal",
        "groups": [GRUPO],
    }
    base.update(extra)
    return base


def resolver(db, **extra):
    return resolver_usuario(
        db.session, claims(**extra), grupo_exigido=GRUPO, admin_mestre=MESTRE
    )


# --- o grupo decide quem entra ---------------------------------------------


def test_sem_o_grupo_nao_entra(db):
    with pytest.raises(SemAcesso):
        resolver(db, groups=["/apps/receita"])


def test_sem_claim_de_grupo_nao_entra(db):
    with pytest.raises(SemAcesso):
        resolver(db, groups=None)


def test_grupo_e_conferido_antes_de_provisionar(db):
    """Provisionar antes de checar abriria o sistema para o realm inteiro."""
    with pytest.raises(SemAcesso):
        resolver(db, groups=[], email="invasor@x.com")
    assert db.session.scalar(select(func.count()).select_from(Usuario)) == 0


def test_com_o_grupo_entra_e_e_provisionado(db):
    usuario = resolver(db)
    db.session.commit()
    assert usuario.email == "fulano@ufcengenharia.com.br"
    assert usuario.external_id == "sub-123"
    assert usuario.perfil == "leitor"
    assert usuario.ativo is True


# --- reconciliacao ----------------------------------------------------------


def test_segunda_visita_reaproveita_o_mesmo_usuario(db):
    primeiro = resolver(db)
    db.session.commit()
    segundo = resolver(db)
    db.session.commit()
    assert primeiro.id == segundo.id
    assert db.session.scalar(select(func.count()).select_from(Usuario)) == 1


def test_usuario_antigo_e_reconciliado_por_email(db):
    """Quem ja existia antes do SSO nao pode virar um segundo cadastro."""
    antigo = Usuario(nome="Fulano", email="fulano@ufcengenharia.com.br", perfil="operador")
    db.session.add(antigo)
    db.session.commit()

    usuario = resolver(db)
    db.session.commit()
    assert usuario.id == antigo.id
    assert usuario.external_id == "sub-123"
    assert usuario.perfil == "operador"  # a promocao local sobrevive ao SSO


def test_troca_de_sub_no_keycloak_nao_duplica(db):
    resolver(db)
    db.session.commit()
    usuario = resolver(db, sub="sub-novo")
    db.session.commit()
    assert db.session.scalar(select(func.count()).select_from(Usuario)) == 1
    assert usuario.external_id == "sub-novo"


def test_email_muda_no_keycloak_e_e_espelhado(db):
    resolver(db)
    db.session.commit()
    usuario = resolver(db, email="fulano.novo@ufcengenharia.com.br")
    db.session.commit()
    assert usuario.email == "fulano.novo@ufcengenharia.com.br"


# --- estado espelhado -------------------------------------------------------


def test_perder_o_grupo_desativa_mas_nao_apaga(db):
    """Despesas e auditoria apontam para o usuario; apagar quebraria o historico."""
    usuario = resolver(db)
    db.session.commit()
    identificador = usuario.id

    with pytest.raises(SemAcesso):
        resolver(db, groups=["/apps/receita"])
    db.session.commit()

    guardado = db.session.get(Usuario, identificador)
    assert guardado is not None
    assert guardado.ativo is False


def test_voltar_ao_grupo_reativa(db):
    resolver(db)
    db.session.commit()
    with pytest.raises(SemAcesso):
        resolver(db, groups=[])
    db.session.commit()

    usuario = resolver(db)
    db.session.commit()
    assert usuario.ativo is True


def test_ultimo_acesso_e_registrado(db):
    usuario = resolver(db)
    db.session.commit()
    assert usuario.ultimo_acesso is not None


# --- conta mestra -----------------------------------------------------------


def test_conta_mestra_entra_sem_grupo(db):
    """Serve justamente para consertar o dia em que alguem se tira do grupo."""
    usuario = resolver(db, email=MESTRE, groups=[])
    db.session.commit()
    assert usuario.perfil == "admin"
    assert usuario.ativo is True


def test_conta_mestra_e_promovida_a_admin_mesmo_se_ja_existia(db):
    db.session.add(Usuario(nome="Mestre", email=MESTRE, perfil="leitor"))
    db.session.commit()
    usuario = resolver(db, email=MESTRE, groups=[])
    db.session.commit()
    assert usuario.perfil == "admin"


def test_comparacao_da_conta_mestra_ignora_caixa(db):
    usuario = resolver(db, email=MESTRE.upper(), groups=[])
    db.session.commit()
    assert usuario.perfil == "admin"


def test_sem_conta_mestra_configurada_ninguem_burla_o_grupo(db):
    with pytest.raises(SemAcesso):
        resolver_usuario(
            db.session, claims(groups=[]), grupo_exigido=GRUPO, admin_mestre=""
        )


# --- token incompleto -------------------------------------------------------


def test_token_sem_email_e_recusado(db):
    with pytest.raises(SemAcesso, match="email"):
        resolver(db, email=None)


def test_token_sem_nome_usa_o_email(db):
    usuario = resolver(db, name=None)
    db.session.commit()
    assert usuario.nome == "fulano@ufcengenharia.com.br"
