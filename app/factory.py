"""Application factory."""

from __future__ import annotations

import os

from flask import Flask, jsonify, render_template, request, session
from markupsafe import Markup

from app import config as configuracao
from app.extensions import csrf, db, limiter, migrate, oauth, sessao

# Sem CDN: tudo vem da propria origem, entao a CSP pode ser fechada.
CSP = {
    "default-src": "'self'",
    "img-src": "'self' data:",
    "style-src": "'self'",
    "script-src": "'self'",
    "form-action": "'self'",
    "frame-ancestors": "'none'",
    "base-uri": "'self'",
}


def create_app(nome_config: str | None = None) -> Flask:
    app = Flask(__name__)
    classe = configuracao.escolher(nome_config)
    app.config.from_object(classe)
    app.config["NOME_CONFIG"] = nome_config or os.environ.get("APP_CONFIG", "dev")
    if hasattr(classe, "validar"):
        classe.validar()

    _registrar_extensoes(app)
    _registrar_filtros(app)
    _registrar_contexto(app)
    _registrar_blueprints(app)
    _registrar_erros(app)
    _registrar_rotas_de_servico(app)
    return app


def classe_de(app: Flask):
    return configuracao.POR_NOME[app.config["NOME_CONFIG"]]


def _registrar_extensoes(app: Flask) -> None:
    db.init_app(app)
    # Povoa db.metadata; sem isto o create_all e o autogenerate ficam vazios.
    from app import models  # noqa: F401

    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)
    oauth.init_app(app)

    if app.config.get("SESSION_TYPE") == "sqlalchemy":
        app.config["SESSION_SQLALCHEMY"] = db
    elif hasattr(classe_de(app), "cache_de_sessao"):
        app.config["SESSION_CACHELIB"] = classe_de(app).cache_de_sessao()
    sessao.init_app(app)

    if app.config.get("OIDC_ISSUER"):
        from app.auth.oidc import registrar_cliente

        registrar_cliente(oauth, app.config)

    from flask_talisman import Talisman

    csp = dict(CSP)
    origem = _origem_do_issuer(app.config.get("OIDC_ISSUER", ""))
    if origem:
        csp["form-action"] = f"'self' {origem}"
    # force_https desligado: a rede nao tem TLS (ver infra/AUDITORIA.md).
    Talisman(
        app,
        force_https=False,
        content_security_policy=csp,
        session_cookie_secure=False,
        strict_transport_security=False,
    )


def _origem_do_issuer(issuer: str) -> str:
    """A CSP precisa da origem do Keycloak em form-action, senao o botao de
    login falha calado."""
    if not issuer:
        return ""
    from urllib.parse import urlsplit

    partes = urlsplit(issuer)
    if not partes.scheme or not partes.netloc:
        return ""
    return f"{partes.scheme}://{partes.netloc}"


def _registrar_filtros(app: Flask) -> None:
    from app.formato import data_curta, moeda, moeda_com_sinal, numero

    app.jinja_env.filters["moeda"] = moeda
    app.jinja_env.filters["sinal"] = moeda_com_sinal
    app.jinja_env.filters["numero"] = numero
    app.jinja_env.filters["data"] = data_curta


def _registrar_contexto(app: Flask) -> None:
    from flask_wtf.csrf import generate_csrf

    from app.auth.guardas import usuario_atual
    from app.sistemas import conta_url, outros_sistemas, portal_url

    @app.context_processor
    def injetar():
        usuario = usuario_atual() if request.endpoint else None
        return {
            "usuario": usuario,
            "portal": portal_url() if usuario else None,
            "conta": conta_url() if usuario else None,
            "outros_sistemas": outros_sistemas(session.get("grupos", [])) if usuario else [],
            "listas": _listas_de_dominio() if usuario else {},
            "form_csrf": lambda: Markup(
                f'<input type="hidden" name="csrf_token" value="{generate_csrf()}">'
            ),
            # O que a pessoa digitou no filtro, e nao o que ele virou depois de
            # resolvido: quem digitou "MEI" nao quer o nome inteiro de volta.
            "termo": lambda chave: request.args.get(chave, ""),
            "selecionados": lambda chave: [v for v in request.args.getlist(chave) if v],
        }


def _listas_de_dominio() -> dict:
    from app.despesas.consulta import opcoes

    try:
        return opcoes(db.session)
    except Exception:  # pragma: no cover - antes da primeira migracao
        return {"centros": [], "naturezas": [], "fornecedores": []}


def _registrar_blueprints(app: Flask) -> None:
    from app.admin.rotas import bp as admin
    from app.auditoria.rotas import bp as auditoria
    from app.auth.rotas import bp as auth
    from app.cli import bp as cli
    from app.despesas.rotas import bp as despesas
    from app.importacao.rotas import bp as importacao
    from app.relatorios.rotas import bp as relatorios

    for blueprint in (auth, despesas, importacao, relatorios, auditoria, admin, cli):
        app.register_blueprint(blueprint)

    # Reconfere o grupo no Keycloak enquanto a sessao esta aberta: sem isto,
    # tirar alguem do grupo so passaria a valer no proximo login.
    from app.auth.revalidacao import instalar

    instalar(app)


def _registrar_erros(app: Flask) -> None:
    from app.auth.guardas import usuario_atual

    @app.errorhandler(403)
    def negado(_erro):
        return render_template(
            "erro.html",
            codigo=403,
            titulo="Sem permissão",
            mensagem="Seu perfil não permite essa ação.",
        ), 403

    @app.errorhandler(404)
    def nao_achou(_erro):
        destino = "erro.html" if usuario_atual() else "auth/entrada.html"
        return render_template(
            destino,
            codigo=404,
            titulo="Não encontrado",
            mensagem="A página ou o registro não existe.",
        ), 404

    @app.errorhandler(413)
    def grande_demais(_erro):
        return render_template(
            "erro.html",
            codigo=413,
            titulo="Arquivo grande demais",
            mensagem="O limite de upload é de 32 MB.",
        ), 413

    @app.errorhandler(500)
    def quebrou(erro):  # pragma: no cover - caminho de excecao
        app.logger.exception("erro nao tratado", exc_info=erro)
        db.session.rollback()
        return render_template(
            "erro.html",
            codigo=500,
            titulo="Algo quebrou",
            mensagem="O erro foi registrado no log do servidor.",
        ), 500


def _registrar_rotas_de_servico(app: Flask) -> None:
    @app.get("/health")
    @limiter.exempt
    @csrf.exempt
    def health():
        """Alvo do HEALTHCHECK do compose; fora da autenticacao."""
        return jsonify(status="ok"), 200
