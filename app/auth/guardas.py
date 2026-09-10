"""Usuario da requisicao e guardas de rota."""

from __future__ import annotations

from functools import wraps

from flask import abort, flash, g, redirect, request, session, url_for

from app.extensions import db
from app.models import Usuario

# Sentinela: distingue "ainda nao consultei" de "consultei e nao ha ninguem".
_NAO_CONSULTADO = object()


def usuario_atual() -> Usuario | None:
    """O usuario da sessao corrente.

    O cache e conferido contra o id da sessao, e nao apenas contra a existencia
    da chave em `g`. O `g` vive no contexto de aplicacao — numa requisicao HTTP
    ele e novo a cada vez, mas num comando de CLI ou num script ele dura o
    processo inteiro, e ai o segundo usuario herdaria o primeiro.
    """
    identificador = session.get("usuario_id")
    if g.get("usuario_da_sessao", _NAO_CONSULTADO) != identificador:
        g.usuario = db.session.get(Usuario, identificador) if identificador else None
        g.usuario_da_sessao = identificador
    return g.usuario


def _recusar(destino: str):
    # Num pedido HTMX, um redirect seria seguido pelo fetch e a tela de login
    # acabaria enfiada dentro de um fragmento. HX-Redirect navega a pagina toda.
    if request.headers.get("HX-Request"):
        resposta = redirect(destino)
        resposta.headers["HX-Redirect"] = destino
        return resposta
    return redirect(destino)


def login_obrigatorio(rota):
    @wraps(rota)
    def envolvida(*args, **kwargs):
        usuario = usuario_atual()
        if usuario is None or not usuario.ativo:
            session.clear()
            return _recusar(url_for("auth.login", proximo=request.full_path))
        return rota(*args, **kwargs)

    return envolvida


def requer(perfil: str):
    """`operador` ou `admin`. Leitor e o piso: basta login_obrigatorio."""
    atributo = {"operador": "pode_escrever", "admin": "pode_administrar"}[perfil]

    def decorador(rota):
        @wraps(rota)
        @login_obrigatorio
        def envolvida(*args, **kwargs):
            if not getattr(usuario_atual(), atributo):
                flash("Seu perfil não permite essa ação.", "erro")
                abort(403)
            return rota(*args, **kwargs)

        return envolvida

    return decorador
