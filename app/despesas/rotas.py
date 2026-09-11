"""Painel, lista e CRUD de despesa."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import select

from app.auditoria.servico import registrar
from app.auth.guardas import login_obrigatorio, requer, usuario_atual
from app.despesas.consulta import (
    agrupamento_da_query,
    chips_do_filtro,
    filtro_da_query,
    opcoes,
    query_sem,
)
from app.despesas.filtros import agrupar, aplicar, totais
from app.extensions import db
from app.formato import mes_curto
from app.graficos import svg
from app.models import CentroCusto, Despesa, Fornecedor, Natureza

bp = Blueprint("despesas", __name__)

POR_PAGINA = 50


@bp.get("/")
@login_obrigatorio
def painel():
    filtro = filtro_da_query(request.args, sessao=db.session)
    resumo = totais(db.session, filtro)

    por_natureza = agrupar(db.session, filtro, por="natureza")
    por_mes = agrupar(db.session, filtro, por="mes")

    grafico_natureza = svg.barras_horizontais(
        [(linha.rotulo, linha.total) for linha in por_natureza],
        titulo="Despesa por natureza",
    )
    grafico_mes = svg.colunas(
        [(_rotulo_de_mes(linha.rotulo), linha.total) for linha in por_mes],
        titulo="Despesa por mês",
    )

    pagina = _pagina(filtro)

    return render_template(
        "despesas/painel.html",
        secao="painel",
        filtro=filtro,
        opcoes=opcoes(db.session),
        resumo=resumo,
        grafico_natureza=grafico_natureza,
        grafico_mes=grafico_mes,
        pagina=pagina,
        chips=chips_do_filtro(request.args),
        meses=len(por_mes),
        periodo_dos_meses=_periodo(por_mes),
        fornecedor_divergente=_fornecedor_das_divergencias(filtro),
        # Sem "divergentes" para o link "ver os divergentes" poder acrescentá-lo;
        # com ele no do relatório, que precisa do recorte inteiro.
        query_base=query_sem(request.args, "pagina", "divergentes"),
        query_completa=query_sem(request.args, "pagina"),
    )


@bp.get("/despesas")
@login_obrigatorio
def lista():
    filtro = filtro_da_query(request.args, sessao=db.session)
    por = agrupamento_da_query(request.args)

    contexto = {
        "secao": "despesas",
        "filtro": filtro,
        "opcoes": opcoes(db.session),
        "resumo": totais(db.session, filtro),
        "pagina": _pagina(filtro),
        "agrupamento": por,
        "grupos": agrupar(db.session, filtro, por=por) if por else None,
        "chips": chips_do_filtro(request.args),
        "query_base": query_sem(request.args, "pagina"),
    }

    # Pedido do HTMX: so a tabela volta, sem o cabecalho e sem os filtros.
    if request.headers.get("HX-Request"):
        return render_template("despesas/_resultado.html", **contexto)
    return render_template("despesas/lista.html", **contexto)


@bp.route("/despesas/nova", methods=["GET", "POST"])
@requer("operador")
def nova():
    if request.method == "GET":
        return render_template("despesas/formulario.html", secao="despesas", despesa=None)

    despesa = Despesa()
    erro = _preencher(despesa, request.form)
    if erro:
        flash(erro, "erro")
        return render_template("despesas/formulario.html", secao="despesas", despesa=None), 400

    db.session.add(despesa)
    db.session.flush()
    despesa.criado_por_id = usuario_atual().id
    registrar(
        db.session,
        acao="despesa.criar",
        usuario=usuario_atual(),
        alvo_tipo="despesa",
        alvo_id=despesa.id,
        payload={"referencia": despesa.referencia, "valor": str(despesa.valor_baixado)},
    )
    db.session.commit()
    flash(f"Despesa {despesa.referencia} criada.", "")
    return _de_volta_para_a_lista()


@bp.route("/despesas/<int:identificador>/editar", methods=["GET", "POST"])
@requer("operador")
def editar(identificador: int):
    despesa = db.session.get(Despesa, identificador) or abort(404)

    if request.method == "GET":
        return render_template("despesas/formulario.html", secao="despesas", despesa=despesa)

    antes = _instantaneo(despesa)
    erro = _preencher(despesa, request.form)
    if erro:
        flash(erro, "erro")
        return render_template("despesas/formulario.html", secao="despesas", despesa=despesa), 400

    registrar(
        db.session,
        acao="despesa.editar",
        usuario=usuario_atual(),
        alvo_tipo="despesa",
        alvo_id=despesa.id,
        payload={"antes": antes, "depois": _instantaneo(despesa)},
    )
    db.session.commit()
    flash(f"Despesa {despesa.referencia} atualizada.", "")
    return _de_volta_para_a_lista()


@bp.post("/despesas/divergencia-em-lote")
@requer("operador")
def divergencia_em_lote():
    """Marca/desmarca varias de uma vez; a selecao atravessa as paginas."""
    ignorar = request.form.get("acao") != "comparar"
    identificadores = {
        int(valor) for valor in request.form.getlist("ids") if valor.isdigit()
    }
    if not identificadores:
        flash("Nenhuma despesa selecionada.", "erro")
        return _de_volta_para_a_lista()

    despesas = db.session.scalars(
        select(Despesa).where(Despesa.id.in_(identificadores))
    ).all()

    mudaram = [d for d in despesas if d.divergencia_ignorada != ignorar]
    for despesa in mudaram:
        despesa.divergencia_ignorada = ignorar

    if mudaram:
        registrar(
            db.session,
            acao="despesa.divergencia",
            usuario=usuario_atual(),
            alvo_tipo="despesa",
            alvo_id=None,
            payload={
                "divergencia_ignorada": ignorar,
                "quantidade": len(mudaram),
                "referencias": sorted(d.referencia for d in mudaram),
            },
        )
    db.session.commit()

    flash(
        f"{len(mudaram)} despesa(s) "
        + ("deixaram de sinalizar divergência." if ignorar else "voltaram a comparar os valores."),
        "",
    )
    return _de_volta_para_a_lista()


@bp.post("/despesas/<int:identificador>/divergencia")
@requer("operador")
def alternar_divergencia(identificador: int):
    """Liga/desliga a comparação entre original e baixado nesta despesa."""
    despesa = db.session.get(Despesa, identificador) or abort(404)
    despesa.divergencia_ignorada = not despesa.divergencia_ignorada

    registrar(
        db.session,
        acao="despesa.divergencia",
        usuario=usuario_atual(),
        alvo_tipo="despesa",
        alvo_id=despesa.id,
        payload={
            "referencia": despesa.referencia,
            "divergencia_ignorada": despesa.divergencia_ignorada,
        },
    )
    db.session.commit()
    flash(
        f"Despesa {despesa.referencia}: "
        + (
            "divergência deixou de ser sinalizada."
            if despesa.divergencia_ignorada
            else "voltou a comparar os valores."
        ),
        "",
    )
    return _de_volta_para_a_lista()


@bp.post("/despesas/<int:identificador>/excluir")
@requer("operador")
def excluir(identificador: int):
    despesa = db.session.get(Despesa, identificador) or abort(404)
    registrar(
        db.session,
        acao="despesa.excluir",
        usuario=usuario_atual(),
        alvo_tipo="despesa",
        alvo_id=despesa.id,
        payload=_instantaneo(despesa),
    )
    db.session.delete(despesa)
    db.session.commit()
    flash(f"Despesa {despesa.referencia} excluída.", "")
    return _de_volta_para_a_lista()


def _de_volta_para_a_lista():
    """A lista com o mesmo recorte de onde a ação partiu."""
    return redirect(url_for("despesas.lista", **query_sem(request.args)))


def _pagina(filtro):
    consulta = aplicar(select(Despesa), filtro)
    # `page` explicito: o db.paginate le a query string sozinho, mas procura por
    # `page`, e as URLs deste sistema usam `pagina`.
    return db.paginate(
        consulta,
        page=request.args.get("pagina", 1, type=int),
        per_page=POR_PAGINA,
        error_out=False,
    )


def _periodo(por_mes) -> str:
    """'mar – ago 2026', para a legenda do grafico."""
    if not por_mes:
        return ""
    primeiro, ultimo = por_mes[0].rotulo, por_mes[-1].rotulo
    if primeiro == ultimo:
        return f"{_rotulo_de_mes(primeiro)}/{primeiro[3:]}"
    if primeiro[3:] == ultimo[3:]:
        return f"{_rotulo_de_mes(primeiro)} – {_rotulo_de_mes(ultimo)} {ultimo[3:]}"
    return f"{_rotulo_de_mes(primeiro)}/{primeiro[3:]} – {_rotulo_de_mes(ultimo)}/{ultimo[3:]}"


def _fornecedor_das_divergencias(filtro) -> str | None:
    """O nome so aparece quando TODAS as divergencias sao do mesmo fornecedor.

    Se vierem de varios, citar um seria enganoso.
    """
    apenas = replace(filtro, somente_divergentes=True)
    nomes = db.session.scalars(
        aplicar(select(Fornecedor.nome).join(Despesa.fornecedor), apenas).distinct().order_by(None)
    ).all()
    return nomes[0] if len(nomes) == 1 else None


def _rotulo_de_mes(rotulo: str) -> str:
    """'03/2026' -> 'mar'."""
    mes, _, _ano = rotulo.partition("/")
    try:
        return mes_curto(int(mes))
    except (ValueError, IndexError):
        return rotulo


def _preencher(despesa: Despesa, form) -> str | None:
    """Devolve a mensagem de erro, ou None se deu tudo certo."""
    from app.despesas.consulta import _data, _decimal, _inteiro

    referencia = _inteiro(form.get("referencia"))
    if referencia is None:
        return "Informe a referência."

    data_baixa = _data(form.get("data_baixa"))
    if data_baixa is None:
        return "Informe a data de baixa."

    valor_baixado = _decimal(form.get("valor_baixado"))
    if valor_baixado is None or valor_baixado < 0:
        return "Informe um valor baixado válido."
    valor_original = _decimal(form.get("valor_original"))
    if valor_original is None:
        valor_original = valor_baixado

    for campo, rotulo in (("centro_custo", "centro de custo"), ("fornecedor", "fornecedor"),
                          ("natureza", "natureza")):
        if not (form.get(campo) or "").strip():
            return f"Informe o {rotulo}."

    centro = CentroCusto.obter_ou_criar(db.session, form["centro_custo"])
    fornecedor = Fornecedor.obter_ou_criar(db.session, form["fornecedor"])
    natureza = Natureza.obter_ou_criar(db.session, form["natureza"])
    historico = (form.get("historico") or "").strip()
    documento = (form.get("documento") or "").strip()
    db.session.flush()

    # A referência sozinha pode repetir; ela junto do resto, não.
    duplicada = db.session.scalars(
        select(Despesa).where(
            Despesa.referencia == referencia,
            Despesa.data_baixa == data_baixa,
            Despesa.fornecedor_id == fornecedor.id,
            Despesa.natureza_id == natureza.id,
            Despesa.centro_custo_id == centro.id,
            Despesa.documento == documento,
            Despesa.historico == historico,
            Despesa.id != (despesa.id or 0),
        )
    ).first()
    if duplicada is not None:
        return (
            f"Já existe um lançamento com a referência {referencia} na mesma data "
            "de baixa e com o mesmo fornecedor, natureza, centro de custo, "
            "documento e histórico."
        )

    despesa.referencia = referencia
    despesa.data_baixa = data_baixa
    despesa.data_emissao = _data(form.get("data_emissao"))
    despesa.centro_custo = centro
    despesa.fornecedor = fornecedor
    despesa.natureza = natureza
    despesa.historico = historico
    despesa.documento = documento
    despesa.valor_original = valor_original
    despesa.valor_baixado = valor_baixado
    despesa.divergencia_ignorada = form.get("divergencia_ignorada") in ("1", "true", "on")
    return None


def _instantaneo(despesa: Despesa) -> dict:
    return {
        "referencia": despesa.referencia,
        "data_baixa": despesa.data_baixa.isoformat() if despesa.data_baixa else None,
        "fornecedor": despesa.fornecedor.nome if despesa.fornecedor else None,
        "natureza": despesa.natureza.nome if despesa.natureza else None,
        "documento": despesa.documento,
        "valor_original": str(despesa.valor_original or Decimal("0")),
        "valor_baixado": str(despesa.valor_baixado or Decimal("0")),
        "divergencia_ignorada": despesa.divergencia_ignorada,
    }
