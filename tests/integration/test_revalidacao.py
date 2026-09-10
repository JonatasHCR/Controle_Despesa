"""Reconferência do grupo durante a sessão.

Conferir o grupo só no login deixa uma janela: tirar a pessoa do
`/apps/controle-despesa` no Keycloak não a expulsava enquanto a sessão durasse —
até 8 horas. O radar e o portal já renovavam o token e reliam os grupos; este
sistema não.

Aqui a renovação é simulada, para os testes não dependerem do Keycloak no ar.
"""

from __future__ import annotations

import time

import pytest

from app.auth import revalidacao

pytestmark = pytest.mark.integration

GRUPO = "/apps/controle-despesa"


@pytest.fixture
def keycloak_falso(monkeypatch):
    """Substitui a ida ao Keycloak por um dicionário controlado pelo teste."""

    estado = {"grupos": [GRUPO], "falhar": False, "chamadas": 0}

    def renovar(_refresh_token):
        estado["chamadas"] += 1
        if estado["falhar"]:
            raise RuntimeError("refresh recusado")
        return {
            "refresh_token": "novo-refresh",
            "expires_in": 300,
            "userinfo": {
                "sub": "sub-leitor",
                "email": "leitor@ufcengenharia.com.br",
                "name": "Leitor",
                "groups": list(estado["grupos"]),
            },
        }

    monkeypatch.setattr(revalidacao, "_renovar_no_keycloak", renovar)
    return estado


@pytest.fixture
def logado(client, leitor):
    """Sessão como quem acabou de entrar pelo Keycloak."""

    def entrar(expira_em_segundos=300):
        with client.session_transaction() as sessao:
            sessao["usuario_id"] = leitor.id
            sessao["grupos"] = [GRUPO]
            sessao["refresh_token"] = "refresh-inicial"
            sessao["expira_em"] = time.time() + expira_em_segundos
        return client

    return entrar


# --- enquanto o token está fresco, nada acontece ----------------------------


def test_token_fresco_nao_conversa_com_o_keycloak(logado, keycloak_falso, carregado):
    """Renovar a cada requisição multiplicaria a carga no Keycloak por nada."""
    cliente = logado(expira_em_segundos=300)
    for _ in range(3):
        assert cliente.get("/despesas").status_code == 200
    assert keycloak_falso["chamadas"] == 0


# --- perto de expirar, renova e relê os grupos ------------------------------


def test_token_perto_de_expirar_e_renovado(logado, keycloak_falso, carregado):
    cliente = logado(expira_em_segundos=30)
    assert cliente.get("/despesas").status_code == 200
    assert keycloak_falso["chamadas"] == 1


def test_renovacao_estende_a_sessao(logado, keycloak_falso, carregado, client):
    cliente = logado(expira_em_segundos=30)
    cliente.get("/despesas")
    with client.session_transaction() as sessao:
        assert sessao["expira_em"] > time.time() + 200
        assert sessao["refresh_token"] == "novo-refresh"


def test_uma_renovacao_serve_para_as_requisicoes_seguintes(logado, keycloak_falso, carregado):
    cliente = logado(expira_em_segundos=30)
    for _ in range(4):
        cliente.get("/despesas")
    assert keycloak_falso["chamadas"] == 1


# --- tirar do grupo passa a valer sem esperar a sessão acabar ---------------


def test_perder_o_grupo_expulsa_na_renovacao(logado, keycloak_falso, carregado, db, leitor):
    cliente = logado(expira_em_segundos=30)
    keycloak_falso["grupos"] = ["/apps/receita"]

    resposta = cliente.get("/despesas")
    assert resposta.status_code == 302
    assert "/auth/login" in resposta.headers["Location"]

    db.session.refresh(leitor)
    assert leitor.ativo is False, "o usuário deveria ter sido desativado"


def test_o_usuario_nao_e_apagado_ao_perder_o_grupo(logado, keycloak_falso, carregado, db, leitor):
    """Despesas e auditoria apontam para ele; apagar quebraria o histórico."""
    identificador = leitor.id
    cliente = logado(expira_em_segundos=30)
    keycloak_falso["grupos"] = []
    cliente.get("/despesas")

    from app.models import Usuario

    assert db.session.get(Usuario, identificador) is not None


def test_voltar_ao_grupo_reativa_na_renovacao(logado, keycloak_falso, carregado, db, leitor):
    cliente = logado(expira_em_segundos=30)
    keycloak_falso["grupos"] = []
    cliente.get("/despesas")
    db.session.refresh(leitor)
    assert leitor.ativo is False

    keycloak_falso["grupos"] = [GRUPO]
    cliente = logado(expira_em_segundos=30)
    assert cliente.get("/despesas").status_code == 200
    db.session.refresh(leitor)
    assert leitor.ativo is True


# --- quando o Keycloak não responde ----------------------------------------


def test_falha_na_renovacao_derruba_a_sessao(logado, keycloak_falso, carregado):
    """Não dá para saber se a pessoa ainda tem acesso: pedir login de novo é a
    resposta segura."""
    cliente = logado(expira_em_segundos=30)
    keycloak_falso["falhar"] = True

    resposta = cliente.get("/despesas")
    assert resposta.status_code == 302
    assert "/auth/login" in resposta.headers["Location"]


def test_sessao_sem_refresh_token_nao_quebra(client, leitor, carregado):
    """Sessão antiga, de antes desta mudança."""
    with client.session_transaction() as sessao:
        sessao["usuario_id"] = leitor.id
        sessao["grupos"] = [GRUPO]
        sessao["expira_em"] = time.time() - 10
    assert client.get("/despesas").status_code == 302


# --- a conta mestra continua entrando --------------------------------------


def test_conta_mestra_sobrevive_sem_o_grupo(app, client, db, keycloak_falso, carregado):
    """Ela existe justamente para consertar o dia em que alguém se tira do grupo."""
    from app.models import Usuario

    mestre = Usuario(
        nome="Mestre",
        email=app.config["ADMIN_MESTRE_EMAIL"] or "admin@ufcengenharia.com.br",
        perfil="admin",
        external_id="sub-mestre",
    )
    db.session.add(mestre)
    db.session.commit()

    app.config["ADMIN_MESTRE_EMAIL"] = mestre.email
    keycloak_falso["grupos"] = []

    def renovar(_refresh):
        return {
            "refresh_token": "novo",
            "expires_in": 300,
            "userinfo": {
                "sub": "sub-mestre",
                "email": mestre.email,
                "name": "Mestre",
                "groups": [],
            },
        }

    revalidacao._renovar_no_keycloak = renovar

    with client.session_transaction() as sessao:
        sessao["usuario_id"] = mestre.id
        sessao["grupos"] = []
        sessao["refresh_token"] = "refresh"
        sessao["expira_em"] = time.time() + 30

    assert client.get("/despesas").status_code == 200


# --- rotas que não exigem sessão -------------------------------------------


def test_health_nao_dispara_renovacao(client, keycloak_falso):
    client.get("/health")
    assert keycloak_falso["chamadas"] == 0


def test_rota_de_login_nao_dispara_renovacao(logado, keycloak_falso, carregado):
    cliente = logado(expira_em_segundos=30)
    cliente.get("/auth/entrada")
    assert keycloak_falso["chamadas"] == 0


# --- o seletor "Sistemas" segue os grupos -----------------------------------


def sistemas_no_menu(corpo: str) -> set[str]:
    import re

    bloco = corpo.split('data-ir-para')[1].split("</select>")[0] if "data-ir-para" in corpo else ""
    return set(re.findall(r"<option value=\"http[^\"]*\">([^<]+)</option>", bloco))


def test_sem_outro_grupo_o_seletor_nao_aparece(entrar, leitor, carregado):
    corpo = entrar(leitor, grupos=[GRUPO]).get("/").get_data(as_text=True)
    assert "data-ir-para" not in corpo


def test_so_aparece_o_sistema_que_a_pessoa_tem(entrar, leitor, carregado):
    cliente = entrar(leitor, grupos=[GRUPO, "/apps/receita"])
    achados = sistemas_no_menu(cliente.get("/").get_data(as_text=True))
    assert achados == {"Receita"}


def test_aparecem_todos_os_que_a_pessoa_tem(entrar, leitor, carregado):
    cliente = entrar(leitor, grupos=[GRUPO, "/apps/receita", "/apps/inventario", "/apps/despesa"])
    achados = sistemas_no_menu(cliente.get("/").get_data(as_text=True))
    assert achados == {"Receita", "Inventário", "Radar"}


def test_o_proprio_sistema_nao_se_lista(entrar, leitor, carregado):
    cliente = entrar(leitor, grupos=[GRUPO, "/apps/receita"])
    achados = sistemas_no_menu(cliente.get("/").get_data(as_text=True))
    assert "Controle de Despesa" not in achados


def test_perder_o_grupo_de_outro_sistema_tira_o_link(logado, keycloak_falso, carregado, client):
    """A renovação reescreve os grupos da sessão; o menu acompanha."""
    with client.session_transaction() as sessao:
        sessao["grupos"] = [GRUPO, "/apps/receita"]
    keycloak_falso["grupos"] = [GRUPO]

    cliente = logado(expira_em_segundos=30)
    with client.session_transaction() as sessao:
        sessao["grupos"] = [GRUPO, "/apps/receita"]

    corpo = cliente.get("/").get_data(as_text=True)
    assert "Receita" not in sistemas_no_menu(corpo)
