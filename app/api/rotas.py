"""API de leitura para o Controle Financeiro (/api/v1).

Só leitura e só para serviço: token Bearer, sem sessão, sem CSRF.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from flask import Blueprint, jsonify, request
from sqlalchemy import func, select

from app.api.token import requer_token
from app.extensions import csrf, db, limiter
from app.models import CentroCusto, Despesa, DespesaExcluida, Fornecedor, Natureza

bp = Blueprint("api", __name__, url_prefix="/api/v1")
csrf.exempt(bp)
limiter.exempt(bp)

LIMITE_PADRAO = 2000
LIMITE_MAXIMO = 5000


def _limite() -> int:
    valor = request.args.get("limit", type=int) or 0
    return LIMITE_PADRAO if valor <= 0 else min(valor, LIMITE_MAXIMO)


def _offset() -> int:
    return max(request.args.get("offset", type=int) or 0, 0)


def _desde(param: str) -> datetime | None:
    valor = request.args.get(param, "").strip()
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None


def _dinheiro(valor: Decimal | None) -> str | None:
    # texto para não perder centavos no JSON
    return None if valor is None else str(valor)


def _iso(valor) -> str | None:
    return valor.isoformat() if valor is not None else None


@bp.get("/despesas")
@requer_token
def despesas():
    consulta = select(Despesa).order_by(Despesa.atualizado_em, Despesa.id)
    marca = _desde("updated_since")
    if marca is not None:
        consulta = consulta.where(Despesa.atualizado_em > marca)
    limite = _limite()
    linhas = db.session.scalars(consulta.limit(limite).offset(_offset())).unique().all()
    return jsonify(
        despesas=[
            {
                "id": d.id,
                "referencia": d.referencia,
                "data_baixa": _iso(d.data_baixa),
                "data_emissao": _iso(d.data_emissao),
                "centro_custo_id": d.centro_custo_id,
                "fornecedor_id": d.fornecedor_id,
                "natureza_id": d.natureza_id,
                "valor_original": _dinheiro(d.valor_original),
                "valor_baixado": _dinheiro(d.valor_baixado),
                "documento": d.documento,
                "historico": d.historico,
                "atualizado_em": _iso(d.atualizado_em),
            }
            for d in linhas
        ],
        watermark=_iso(linhas[-1].atualizado_em) if linhas else None,
        count=len(linhas),
        has_more=len(linhas) == limite,
    )


@bp.get("/despesas/exclusoes")
@requer_token
def exclusoes():
    consulta = select(DespesaExcluida).order_by(
        DespesaExcluida.excluida_em, DespesaExcluida.despesa_id
    )
    marca = _desde("since")
    if marca is not None:
        consulta = consulta.where(DespesaExcluida.excluida_em > marca)
    limite = _limite()
    linhas = db.session.scalars(consulta.limit(limite)).all()
    return jsonify(
        exclusoes=[{"id": x.despesa_id, "excluida_em": _iso(x.excluida_em)} for x in linhas],
        watermark=_iso(linhas[-1].excluida_em) if linhas else None,
        count=len(linhas),
        has_more=len(linhas) == limite,
    )


@bp.get("/despesas/ids")
@requer_token
def ids():
    """Todos os ids existentes, para o Controle Financeiro apagar o que sobrou na cópia."""
    return jsonify(ids=db.session.scalars(select(Despesa.id).order_by(Despesa.id)).all())


def _dominio(modelo, extras=lambda _x: {}):
    linhas = db.session.scalars(select(modelo).order_by(modelo.id)).all()
    return [{"id": x.id, "nome": x.nome, "ativo": x.ativo, **extras(x)} for x in linhas]


@bp.get("/centros_custo")
@requer_token
def centros_custo():
    return jsonify(centros_custo=_dominio(CentroCusto, lambda c: {"codigo": c.codigo}))


@bp.get("/fornecedores")
@requer_token
def fornecedores():
    return jsonify(fornecedores=_dominio(Fornecedor))


@bp.get("/naturezas")
@requer_token
def naturezas():
    return jsonify(naturezas=_dominio(Natureza))


@bp.get("/status")
@requer_token
def status():
    contagem, maior, soma, maior_id = db.session.execute(
        select(
            func.count(Despesa.id),
            func.max(Despesa.atualizado_em),
            func.coalesce(func.sum(Despesa.valor_baixado), 0),
            func.max(Despesa.id),
        )
    ).one()
    return jsonify(
        despesas={
            "count": contagem,
            "max_updated_at": _iso(maior),
            "sum_valor_baixado": _dinheiro(soma),
            "max_id": maior_id,
        },
        centros_custo={"count": db.session.scalar(select(func.count(CentroCusto.id)))},
        fornecedores={"count": db.session.scalar(select(func.count(Fornecedor.id)))},
        naturezas={"count": db.session.scalar(select(func.count(Natureza.id)))},
    )
