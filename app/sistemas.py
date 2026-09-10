"""Catalogo dos sistemas da plataforma, para o seletor "Sistemas".

Duplicado de proposito em cada app (o portal tem o seu, a receita o dela): sao
poucas linhas, e um pacote compartilhado exigiria publicar e versionar.
"""

from __future__ import annotations

from flask import current_app

GRUPO_DESTE_SISTEMA = "/apps/controle-despesa"


def _host() -> str:
    return f"http://{current_app.config['HOST_IP']}"


def portal_url() -> str:
    return f"{_host()}:{current_app.config['PORTAL_PORT']}"


def url_publica(caminho: str = "") -> str:
    """URL deste sistema como o mundo o alcanca.

    Nao se monta a partir da requisicao: dentro do container o Host e o que o
    cliente mandou (localhost, o nome do servico, o IP), e o redirect_uri
    precisa bater exatamente com o registrado no realm. E a mesma regra que os
    apps Next da plataforma seguem com o baseUrl().
    """
    base = f"{_host()}:{current_app.config['PORTA_PUBLICA']}"
    return f"{base}{caminho}" if caminho else base


def sistemas() -> list[dict]:
    return [
        {
            "grupo": "/apps/inventario",
            "nome": "Inventário",
            "url": f"{_host()}:{current_app.config['INVENTARIO_PORT']}",
        },
        {
            "grupo": "/apps/receita",
            "nome": "Receita",
            "url": f"{_host()}:{current_app.config['RECEITA_PORT']}",
        },
        {
            "grupo": "/apps/despesa",
            "nome": "Radar",
            "url": f"{_host()}:{current_app.config['DESPESA_PORT']}",
        },
    ]


def outros_sistemas(grupos: list[str]) -> list[dict]:
    return [
        sistema
        for sistema in sistemas()
        if sistema["grupo"] != GRUPO_DESTE_SISTEMA and sistema["grupo"] in grupos
    ]
