"""Login, callback e logout — o fluxo OIDC contra o Keycloak."""

from __future__ import annotations

from urllib.parse import urlencode

from flask import Blueprint, current_app, flash, redirect, render_template, session, url_for

from app.auth.oidc import SemAcesso, resolver_usuario
from app.auth.revalidacao import guardar_sessao
from app.extensions import db, limiter, oauth
from app.sistemas import portal_url, url_publica

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.get("/login")
@limiter.limit("30 per minute")
def login():
    session["proximo"] = _destino_seguro()
    return oauth.keycloak.authorize_redirect(url_publica("/auth/callback"))


@bp.get("/callback")
@limiter.limit("30 per minute")
def callback():
    # O Keycloak sinaliza erro por query string, nao por status HTTP.
    from flask import request

    if request.args.get("error"):
        motivo = request.args.get("error_description") or request.args["error"]
        flash(f"O login falhou: {motivo}", "erro")
        return redirect(url_for("auth.entrada"))

    token = oauth.keycloak.authorize_access_token()
    claims = token.get("userinfo") or {}

    try:
        usuario = resolver_usuario(
            db.session,
            claims,
            grupo_exigido=current_app.config["OIDC_REQUIRED_GROUP"],
            admin_mestre=current_app.config["ADMIN_MESTRE_EMAIL"],
        )
    except SemAcesso as erro:
        db.session.commit()  # a desativacao precisa persistir
        current_app.logger.info("acesso negado a %s: %s", claims.get("email"), erro)
        return render_template("auth/sem_acesso.html", portal=portal_url()), 403

    db.session.commit()

    proximo = session.pop("proximo", None)
    session.clear()
    guardar_sessao(usuario, token, claims)

    return redirect(proximo or url_for("despesas.painel"))


@bp.get("/logout")
def logout():
    id_token = session.get("id_token")
    session.clear()

    # Sem client_id nem id_token_hint o Keycloak nao sabe contra qual client
    # validar o destino, e devolve 400.
    fim = current_app.config["OIDC_ISSUER"] + "/protocol/openid-connect/logout"
    parametros = {
        "client_id": current_app.config["OIDC_CLIENT_ID"],
        "post_logout_redirect_uri": portal_url(),
    }
    if id_token:
        parametros["id_token_hint"] = id_token
    return redirect(f"{fim}?{urlencode(parametros)}")


@bp.get("/entrada")
def entrada():
    """Pagina com o botao de entrar, para quem chega deslogado."""
    return render_template("auth/entrada.html")


def _destino_seguro() -> str | None:
    """So caminhos internos: um `proximo` absoluto viraria open redirect."""
    from flask import request

    destino = request.args.get("proximo") or ""
    if destino.startswith("/") and not destino.startswith("//"):
        return destino
    return None
