"""Configuracao por ambiente."""

from __future__ import annotations

import os
from datetime import timedelta


def _obrigatoria(nome: str) -> str:
    valor = os.environ.get(nome)
    if not valor:
        raise RuntimeError(f"variavel de ambiente obrigatoria ausente: {nome}")
    return valor


def _uri_postgres(banco_padrao: str | None = None) -> str:
    usuario = os.environ.get("POSTGRES_USER", "controle_despesa")
    senha = os.environ.get("POSTGRES_PASSWORD", "controle_despesa")
    host = os.environ.get("DB_HOST", "db")
    porta = os.environ.get("DB_PORT", "5432")
    banco = banco_padrao or os.environ.get("POSTGRES_DB", "controle_despesa")
    return f"postgresql+psycopg://{usuario}:{senha}@{host}:{porta}/{banco}"


class Base:
    # --- Flask -----------------------------------------------------------
    SECRET_KEY = os.environ.get("SESSION_SECRET", "dev-inseguro-troque-no-env")
    JSON_SORT_KEYS = False
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024

    # --- Banco -----------------------------------------------------------
    SQLALCHEMY_DATABASE_URI = _uri_postgres()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # --- Sessao ----------------------------------------------------------
    # No banco, nao no cookie: com cinco apps no mesmo host o navegador manda
    # os cookies de todos para cada um e o header estoura.
    SESSION_TYPE = "sqlalchemy"
    SESSION_SQLALCHEMY_TABLE = "tb_sessoes"
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)  # = ssoSessionIdleTimeout
    SESSION_COOKIE_NAME = "controle_despesa_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False  # sem TLS nessa rede (infra/AUDITORIA.md)

    # --- OIDC / Keycloak -------------------------------------------------
    OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "")
    OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "controle-despesa-web")
    OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")
    OIDC_REQUIRED_GROUP = os.environ.get("OIDC_REQUIRED_GROUP", "/apps/controle-despesa")
    ADMIN_MESTRE_EMAIL = os.environ.get("ADMIN_MESTRE_EMAIL", "")

    # --- Portal e sistemas irmaos ---------------------------------------
    HOST_IP = os.environ.get("HOST_IP", "localhost")
    PORTA_PUBLICA = os.environ.get("PORTA_PUBLICA", "3050")
    PORTAL_PORT = os.environ.get("PORTAL_PORT", "3080")
    INVENTARIO_PORT = os.environ.get("INVENTARIO_PORT", "3030")
    RECEITA_PORT = os.environ.get("RECEITA_PORT", "3040")
    DESPESA_PORT = os.environ.get("DESPESA_PORT", "3010")

    # --- Rate limit ------------------------------------------------------
    # Em memoria, por worker. Nao ha Redis nessa infra, e o alvo aqui e conter
    # abuso de importacao e de relatorio por usuario autenticado numa LAN.
    RATELIMIT_STORAGE_URI = "memory://"
    RATELIMIT_HEADERS_ENABLED = True

    # --- Backup ----------------------------------------------------------
    BACKUP_DIR = os.environ.get("BACKUP_DIR", "/backups")

    TESTING = False
    DEBUG = False


class Dev(Base):
    DEBUG = True


class Test(Base):
    TESTING = True
    # Postgres de verdade, nao SQLite: ILIKE, date_trunc e IS DISTINCT FROM
    # precisam se comportar como em producao.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URI",
        _uri_postgres(os.environ.get("POSTGRES_DB_TEST", "controle_despesa_test")),
    )
    SECRET_KEY = "teste"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False

    SESSION_TYPE = "cachelib"

    @staticmethod
    def cache_de_sessao():
        from cachelib.simple import SimpleCache

        return SimpleCache(threshold=500)


class Prod(Base):
    @classmethod
    def validar(cls) -> None:
        _obrigatoria("SESSION_SECRET")
        _obrigatoria("OIDC_ISSUER")
        _obrigatoria("OIDC_CLIENT_SECRET")


POR_NOME = {"dev": Dev, "test": Test, "prod": Prod}


def escolher(nome: str | None = None):
    nome = nome or os.environ.get("APP_CONFIG", "dev")
    if nome not in POR_NOME:
        raise RuntimeError(f"APP_CONFIG desconhecido: {nome!r} (use dev, test ou prod)")
    return POR_NOME[nome]
