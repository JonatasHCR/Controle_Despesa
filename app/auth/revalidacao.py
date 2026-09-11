"""Reconferência do grupo enquanto a sessão está aberta.

Sem isto, tirar a pessoa do grupo no Keycloak só passaria a valer no próximo
login — aqui, até 8 horas depois.
"""

from __future__ import annotations

import time

from flask import current_app, session

from app.auth.oidc import SemAcesso, resolver_usuario
from app.extensions import db, oauth

# Mesma margem do middleware do radar, para os dois expulsarem no mesmo ritmo.
MARGEM_SEGUNDOS = 60


def _renovar_no_keycloak(refresh_token: str) -> dict:
    """`fetch_access_token` nao preenche `userinfo`; so o do login faz."""
    token = oauth.keycloak.fetch_access_token(
        grant_type="refresh_token", refresh_token=refresh_token
    )
    token["userinfo"] = oauth.keycloak.userinfo(token=token)
    return token


def guardar_sessao(usuario, token: dict, claims: dict) -> None:
    session["usuario_id"] = usuario.id
    session["grupos"] = claims.get("groups") or []
    session["id_token"] = token.get("id_token")
    session["refresh_token"] = token.get("refresh_token")
    session["expira_em"] = time.time() + float(token.get("expires_in") or 300)
    session.permanent = True


def precisa_renovar() -> bool:
    if "usuario_id" not in session:
        return False
    expira_em = session.get("expira_em")
    if expira_em is None:
        return False
    return float(expira_em) - MARGEM_SEGUNDOS <= time.time()


def revalidar() -> bool:
    """Renova o token e reconfere o grupo. False quando o acesso acabou.

    Falha de rede também devolve False: sem resposta do Keycloak não dá para
    afirmar que a pessoa ainda tem acesso.
    """
    refresh_token = session.get("refresh_token")
    if not refresh_token:
        return False

    try:
        token = _renovar_no_keycloak(refresh_token)
    except Exception as erro:
        current_app.logger.info("renovação de token falhou: %s", erro)
        return False

    claims = token.get("userinfo") or {}
    if not claims:
        return False

    try:
        usuario = resolver_usuario(
            db.session,
            claims,
            grupo_exigido=current_app.config["OIDC_REQUIRED_GROUP"],
            admin_mestre=current_app.config["ADMIN_MESTRE_EMAIL"],
        )
    except SemAcesso as erro:
        db.session.commit()  # a desativação persiste mesmo com a sessão indo embora
        current_app.logger.info("acesso revogado para %s: %s", claims.get("email"), erro)
        return False

    db.session.commit()
    guardar_sessao(usuario, token, claims)
    return True


def instalar(app) -> None:
    from flask import g, redirect, request, url_for

    ISENTAS = {"health", "static", "auth.login", "auth.callback", "auth.logout", "auth.entrada"}

    @app.before_request
    def reconferir_grupo():
        if request.endpoint in ISENTAS or request.endpoint is None:
            return None
        if not precisa_renovar():
            return None

        if revalidar():
            g.pop("usuario", None)
            g.pop("usuario_da_sessao", None)
            return None

        session.clear()
        # `proximo` so para GET: o callback volta sempre com GET, e devolver a
        # pessoa a uma rota POST-only daria 405 em vez da tela dela.
        proximo = request.full_path if request.method == "GET" else None
        destino = url_for("auth.login", proximo=proximo)
        if request.headers.get("HX-Request"):
            resposta = redirect(destino)
            resposta.headers["HX-Redirect"] = destino
            return resposta
        return redirect(destino)
