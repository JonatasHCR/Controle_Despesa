"""O minimo que precisa estar de pe antes de qualquer outra coisa."""

import pytest


@pytest.mark.integration
def test_health_responde_ok(client):
    resposta = client.get("/health")
    assert resposta.status_code == 200
    assert resposta.get_json() == {"status": "ok"}


@pytest.mark.integration
def test_health_fica_fora_da_autenticacao(client):
    """E alvo do HEALTHCHECK do compose: nao pode exigir sessao."""
    assert client.get("/health").status_code == 200


@pytest.mark.integration
def test_csp_nao_libera_inline(client):
    """Sem CDN nessa rede, a CSP pode ser fechada — e deve continuar sendo."""
    csp = client.get("/health").headers.get("Content-Security-Policy", "")
    assert "'unsafe-inline'" not in csp
    assert "default-src 'self'" in csp
