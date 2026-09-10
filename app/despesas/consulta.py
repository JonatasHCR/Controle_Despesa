"""Traducao da query string em Filtro, e as opcoes dos combos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from app.despesas.filtros import AGRUPAMENTOS, ORDENS, Filtro, curinga
from app.models import CentroCusto, Fornecedor, Natureza


def filtro_da_query(args, *, sessao=None) -> Filtro:
    """Monta o Filtro a partir de `request.args`.

    Entrada invalida vira ausencia de filtro, nunca erro 500: a query string e
    editavel na barra de enderecos, e uma data mal digitada nao pode derrubar a
    tela.

    Com `sessao`, os campos de dominio aceitam termo parcial — quem digita
    "MEI" acha "SERVIÇOS ESPECIALIZADOS MEI". A resolucao acontece aqui, e nao
    no motor de filtro: ele continua comparando por igualdade, que e o que
    impede "SERVIÇOS DE ORÇAMENTO" de arrastar "SERVIÇOS DIVERSOS".
    """
    ordem = args.get("ordem", "data")
    return Filtro(
        inicio=_data(args.get("inicio")),
        fim=_data(args.get("fim")),
        campo_data="data_emissao" if args.get("campo_data") == "data_emissao" else "data_baixa",
        centros=_resolver(sessao, CentroCusto, CentroCusto.codigo, _lista(args, "centro")),
        naturezas=_resolver(sessao, Natureza, Natureza.nome, _lista(args, "natureza")),
        fornecedores=_resolver(sessao, Fornecedor, Fornecedor.nome, _lista(args, "fornecedor")),
        documento=(args.get("documento") or "").strip(),
        referencia=(args.get("referencia") or "").strip(),
        busca=(args.get("busca") or "").strip(),
        valor_minimo=_decimal(args.get("valor_minimo")),
        valor_maximo=_decimal(args.get("valor_maximo")),
        somente_divergentes=args.get("divergentes") in ("1", "true", "on"),
        ordem=ordem if ordem in ORDENS else "data",
        decrescente=args.get("desc") in ("1", "true", "on"),
    )


def _resolver(sessao, modelo, coluna, termos: list[str]) -> list[str]:
    """Expande cada termo digitado nos nomes que ele alcanca.

    Termo que ja e um nome exato fica como esta — o caminho de quem escolheu da
    lista nao paga round-trip nem muda de comportamento.
    """
    termos = [termo.strip() for termo in termos if termo.strip()]
    if not termos or sessao is None:
        return termos

    resolvidos: list[str] = []
    for termo in termos:
        exato = sessao.scalars(select(coluna).where(coluna == termo)).first()
        if exato is not None:
            resolvidos.append(exato)
            continue
        parecidos = sessao.scalars(
            select(coluna).where(coluna.ilike(curinga(termo), escape="\\")).order_by(coluna)
        ).all()
        # Nenhum parecido: mantem o termo, e o filtro devolve vazio — que e a
        # resposta certa para "fornecedor que nao existe".
        resolvidos.extend(parecidos or [termo])
    return resolvidos


# --- chips do recorte ativo -------------------------------------------------

# Nao sao filtro: agrupar muda a apresentacao, e pagina/ordem a navegacao.
FORA_DO_RECORTE = {"agrupar", "pagina", "ordem", "desc", "campo_data"}

ROTULOS = {
    "centro": "Centro de custo",
    "natureza": "Natureza",
    "fornecedor": "Fornecedor",
    "referencia": "Referência",
    "documento": "Documento",
    "busca": "Busca",
}


@dataclass(frozen=True)
class Chip:
    rotulo: str
    valor: str
    sem: dict


def chips_do_filtro(args) -> list[Chip]:
    """O recorte ativo em uma linha, cada pedaco removivel."""
    presentes = {
        chave: valor
        for chave, valor in args.items()
        if valor and chave not in FORA_DO_RECORTE
    }
    lista: list[Chip] = []

    def sem(*chaves: str) -> dict:
        # A pagina sai junto: sair de um filtro na pagina 3 poderia cair fora
        # do resultado novo.
        restante = {c: v for c, v in args.items() if v and c not in chaves and c != "pagina"}
        return restante

    inicio, fim = _data(presentes.get("inicio")), _data(presentes.get("fim"))
    if inicio or fim:
        rotulo = "Emissão" if args.get("campo_data") == "data_emissao" else "Baixa"
        if inicio and fim:
            valor = f"{_curta(inicio)} – {_curta(fim)}"
        elif inicio:
            valor = f"a partir de {_curta(inicio)}"
        else:
            valor = f"até {_curta(fim)}"
        lista.append(Chip(rotulo, valor, sem("inicio", "fim")))

    for chave in ("centro", "natureza", "fornecedor", "referencia", "documento", "busca"):
        valor = presentes.get(chave)
        if valor:
            lista.append(Chip(ROTULOS[chave], valor, sem(chave)))

    minimo, maximo = presentes.get("valor_minimo"), presentes.get("valor_maximo")
    if minimo or maximo:
        if minimo and maximo:
            valor = f"{minimo} – {maximo}"
        elif minimo:
            valor = f"a partir de {minimo}"
        else:
            valor = f"até {maximo}"
        lista.append(Chip("Valor", valor, sem("valor_minimo", "valor_maximo")))

    if presentes.get("divergentes") in ("1", "true", "on"):
        lista.append(Chip("Somente divergentes", "", sem("divergentes")))

    return lista


def _curta(valor: date) -> str:
    return f"{valor.day:02d}/{valor.month:02d}/{valor.year}"


def agrupamento_da_query(args) -> str | None:
    por = args.get("agrupar") or ""
    return por if por in AGRUPAMENTOS else None


def opcoes(session) -> dict:
    """O que alimenta as listas de busca dos filtros."""
    return {
        "centros": session.scalars(select(CentroCusto.codigo).order_by(CentroCusto.codigo)).all(),
        "naturezas": session.scalars(select(Natureza.nome).order_by(Natureza.nome)).all(),
        "fornecedores": session.scalars(select(Fornecedor.nome).order_by(Fornecedor.nome)).all(),
    }


def query_sem(args, *remover: str) -> dict:
    """Copia da query string sem certas chaves — para montar links de paginacao."""
    return {chave: valor for chave, valor in args.items(multi=True) if chave not in remover}


def _data(texto: str | None) -> date | None:
    if not texto:
        return None
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto.strip(), formato).date()
        except ValueError:
            continue
    return None


def _inteiro(texto: str | None) -> int | None:
    try:
        return int(str(texto).strip())
    except (TypeError, ValueError):
        return None


def _decimal(texto: str | None) -> Decimal | None:
    if not texto:
        return None
    limpo = str(texto).strip().replace(".", "").replace(",", ".")
    try:
        return Decimal(limpo)
    except InvalidOperation:
        return None


def _lista(args, chave: str) -> list[str]:
    return [valor for valor in args.getlist(chave) if valor]
