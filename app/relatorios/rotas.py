"""Montagem e download do relatorio."""

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from sqlalchemy import select

from app.auditoria.servico import registrar
from app.auth.guardas import login_obrigatorio, usuario_atual
from app.despesas.consulta import (
    agrupamento_da_query,
    chips_do_filtro,
    filtro_da_query,
    opcoes,
    query_sem,
)
from app.despesas.filtros import agrupar, aplicar, totais
from app.extensions import db, limiter
from app.formato import data_curta
from app.models import Despesa
from app.relatorios import excel, pdf

bp = Blueprint("relatorios", __name__, url_prefix="/relatorios")

TITULOS = {
    "natureza": "Natureza",
    "fornecedor": "Fornecedor",
    "centro": "Centro de custo",
    "ano": "Ano",
    "mes": "Mês",
    "dia": "Dia",
}

TIPOS = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


@bp.get("/")
@login_obrigatorio
def montar():
    filtro = filtro_da_query(request.args, sessao=db.session)
    por = agrupamento_da_query(request.args)
    return render_template(
        "relatorios/montar.html",
        secao="relatorios",
        filtro=filtro,
        agrupamento=por,
        opcoes=opcoes(db.session),
        resumo=totais(db.session, filtro),
        grupos=agrupar(db.session, filtro, por=por) if por else None,
        titulo_do_grupo=TITULOS.get(por, ""),
        chips=chips_do_filtro(request.args),
        query_base=query_sem(request.args, "pagina"),
    )


@bp.get("/<formato>")
@login_obrigatorio
@limiter.limit("20 per minute")
def baixar(formato: str):
    if formato not in TIPOS:
        return render_template("erro.html", codigo=404, titulo="Formato desconhecido",
                               mensagem="Use xlsx ou pdf."), 404

    filtro = filtro_da_query(request.args, sessao=db.session)
    por = agrupamento_da_query(request.args)

    despesas = db.session.scalars(aplicar(select(Despesa), filtro)).all()
    resumo = totais(db.session, filtro)
    grupos = agrupar(db.session, filtro, por=por) if por else None
    descricao = descrever(filtro, por)

    gerador = excel if formato == "xlsx" else pdf
    try:
        conteudo = gerador.gerar(
            despesas,
            resumo,
            descricao_do_filtro=descricao,
            grupos=grupos,
            titulo_do_grupo=TITULOS.get(por, ""),
        )
    except pdf.RelatorioGrandeDemais as erro:
        flash(str(erro), "atencao")
        return redirect(url_for("relatorios.montar", **query_sem(request.args)))

    registrar(
        db.session,
        acao=f"relatorio.{formato}",
        usuario=usuario_atual(),
        alvo_tipo="relatorio",
        payload={"filtro": descricao, "lancamentos": resumo.lancamentos, "agrupamento": por},
    )
    db.session.commit()

    nome = f"controle-despesa-{datetime.now():%Y%m%d-%H%M}.{formato}"
    return Response(
        conteudo,
        mimetype=TIPOS[formato],
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


def descrever(filtro, agrupamento: str | None) -> str:
    """O filtro em uma linha, impresso no relatorio.

    Sem isso, um PDF encaminhado por e-mail nao diz de que recorte ele saiu.
    """
    partes = []

    rotulo_data = "emissão" if filtro.campo_data == "data_emissao" else "baixa"
    if filtro.inicio and filtro.fim:
        partes.append(f"{rotulo_data} de {data_curta(filtro.inicio)} a {data_curta(filtro.fim)}")
    elif filtro.inicio:
        partes.append(f"{rotulo_data} a partir de {data_curta(filtro.inicio)}")
    elif filtro.fim:
        partes.append(f"{rotulo_data} até {data_curta(filtro.fim)}")

    if filtro.centros:
        partes.append("centro de custo " + ", ".join(filtro.centros))
    if filtro.naturezas:
        partes.append("natureza " + ", ".join(filtro.naturezas))
    if filtro.fornecedores:
        partes.append("fornecedor " + ", ".join(filtro.fornecedores))
    if filtro.documento:
        partes.append(f"documento contendo “{filtro.documento}”")
    if filtro.referencia is not None:
        partes.append(f"referência {filtro.referencia}")
    if filtro.busca:
        partes.append(f"busca “{filtro.busca}”")
    if filtro.valor_minimo is not None:
        partes.append(f"valor a partir de {filtro.valor_minimo}")
    if filtro.valor_maximo is not None:
        partes.append(f"valor até {filtro.valor_maximo}")
    if filtro.somente_divergentes:
        partes.append("somente divergentes")

    texto = "Todos os lançamentos" if not partes else "Filtro: " + "; ".join(partes)
    if agrupamento:
        texto += f" · agrupado por {TITULOS[agrupamento].lower()}"
    return texto + f" · emitido em {data_curta(datetime.now().date())}"
