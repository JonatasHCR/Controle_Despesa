"""As URLs que saem para o mundo vêm do HOST_IP, nunca da requisicao.

Regressao de um bug real: com `url_for(..., _external=True)` o redirect_uri era
montado a partir do cabecalho Host. Quem abrisse por localhost mandava
`http://localhost:3050/auth/callback`, que nao bate com o registrado no realm, e
o Keycloak respondia 400 antes de mostrar a tela de login.
"""

from __future__ import annotations

import pytest

from app.sistemas import portal_url, url_publica

pytestmark = pytest.mark.integration


@pytest.fixture
def contexto(app):
    app.config["HOST_IP"] = "10.0.0.143"
    app.config["PORTA_PUBLICA"] = "3050"
    app.config["PORTAL_PORT"] = "3080"
    return app


def test_url_publica_usa_o_host_ip(contexto):
    with contexto.test_request_context():
        assert url_publica() == "http://10.0.0.143:3050"
        assert url_publica("/auth/callback") == "http://10.0.0.143:3050/auth/callback"


@pytest.mark.parametrize("host", ["localhost:3050", "web:8000", "0.0.0.0:8000", "outro.nome"])
def test_url_publica_ignora_o_cabecalho_host(contexto, host):
    """E o cerne do bug: dentro do container o Host e o que o cliente mandou."""
    with contexto.test_request_context(headers={"Host": host}):
        assert url_publica("/auth/callback") == "http://10.0.0.143:3050/auth/callback"


def test_portal_url_tambem_ignora_o_host(contexto):
    with contexto.test_request_context(headers={"Host": "localhost:3050"}):
        assert portal_url() == "http://10.0.0.143:3080"


def test_login_manda_o_redirect_uri_do_host_ip(contexto, client):
    """O caminho completo: a rota /auth/login precisa levar o redirect_uri certo
    ate o Keycloak."""
    contexto.config["OIDC_ISSUER"] = "http://10.0.0.143:8080/realms/ufc"
    from urllib.parse import parse_qs, urlsplit

    from app.auth.oidc import registrar_cliente
    from app.extensions import oauth

    if not hasattr(oauth, "keycloak"):
        registrar_cliente(oauth, contexto.config)

    resposta = client.get("/auth/login", headers={"Host": "localhost:3050"})
    if resposta.status_code != 302:
        pytest.skip("sem Keycloak alcancavel para o discovery")

    destino = resposta.headers["Location"]
    parametros = parse_qs(urlsplit(destino).query)
    assert parametros["redirect_uri"] == ["http://10.0.0.143:3050/auth/callback"]
