"""Cliente OIDC e resolucao do usuario local a partir do token."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from app.models import Usuario


class SemAcesso(Exception):
    """O token e valido, mas esta pessoa nao pode usar este sistema."""


def registrar_cliente(oauth, config) -> None:
    oauth.register(
        name="keycloak",
        client_id=config["OIDC_CLIENT_ID"],
        client_secret=config["OIDC_CLIENT_SECRET"],
        server_metadata_url=f"{config['OIDC_ISSUER']}/.well-known/openid-configuration",
        client_kwargs={"scope": "openid profile email", "code_challenge_method": "S256"},
    )


def resolver_usuario(session, claims: dict, *, grupo_exigido: str, admin_mestre: str) -> Usuario:
    """Traduz as claims num usuario local, ou levanta SemAcesso.

    A conferencia do grupo vem ANTES de qualquer provisionamento: ao contrario,
    o cadastro automatico abriria o sistema para o realm inteiro.
    """
    email = (claims.get("email") or "").strip()
    if not email:
        raise SemAcesso("o token nao trouxe email")

    mestre = bool(admin_mestre) and email.lower() == admin_mestre.strip().lower()
    grupos = claims.get("groups") or []
    tem_acesso = mestre or grupo_exigido in grupos

    usuario = _localizar(session, claims.get("sub"), email)

    if not tem_acesso:
        if usuario is not None:
            # Nunca se apaga: despesas e auditoria apontam para ele.
            usuario.ativo = False
        raise SemAcesso(f"falta o grupo {grupo_exigido}")

    if usuario is None:
        usuario = Usuario(nome=_nome(claims, email), email=email, perfil="leitor")
        session.add(usuario)

    usuario.external_id = claims.get("sub") or usuario.external_id
    usuario.email = email
    usuario.nome = _nome(claims, email)
    usuario.ativo = True
    usuario.ultimo_acesso = datetime.now(UTC)
    if mestre:
        usuario.perfil = "admin"

    session.flush()
    return usuario


def _localizar(session, sub: str | None, email: str) -> Usuario | None:
    if sub:
        achado = session.scalars(select(Usuario).where(Usuario.external_id == sub)).first()
        if achado is not None:
            return achado
    # Quem ja existia antes do SSO foi cadastrado por email; sem esta queda o
    # primeiro login criaria um segundo cadastro e perderia o perfil.
    return session.scalars(
        select(Usuario).where(func.lower(Usuario.email) == email.lower())
    ).first()


def _nome(claims: dict, email: str) -> str:
    return (claims.get("name") or "").strip() or email
