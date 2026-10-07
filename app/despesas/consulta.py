"""Traducao da query string em Filtro, e as opcoes dos combos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from app.despesas.filtros import AGRUPAMENTOS, ORDENS, Filtro, curinga
from app.models import CentroCusto, Fornecedor, Natureza

LIMITE_DE_IDS = 5000


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
        ids=[int(v) for v in args.getlist("id") if v.isdigit()][:LIMITE_DE_IDS],
        ordem=ordem if ordem in ORDENS else "data",
        # Sem `desc` na URL, o padrao e decrescente: a tela abre nas despesas
        # mais recentes, que e o que se quer ver primeiro.
        decrescente=(args["desc"] in ("1", "true", "on") if "desc" in args else True),
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
FORA_DO_RECORTE = {"agrupar", "pagina", "ordem", "desc", "campo_data", "id"}

MULTIPLOS = ("centro", "natureza", "fornecedor")

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
        chave: valor for chave, valor in args.items() if valor and chave not in FORA_DO_RECORTE
    }
    lista: list[Chip] = []

    def sem(*chaves: str) -> dict:
        # A pagina sai junto: sair de um filtro na pagina 3 poderia cair fora
        # do resultado novo.
        return {
            chave: valores
            for chave, valores in todos_os_valores(args).items()
            if chave not in chaves and chave != "pagina"
        }

    def sem_o_valor(chave: str, alvo: str) -> dict:
        restante = sem()
        sobrou = [valor for valor in restante.get(chave, []) if valor != alvo]
        if sobrou:
            restante[chave] = sobrou
        else:
            restante.pop(chave, None)
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

    for chave in MULTIPLOS:
        for valor in _lista(args, chave):
            lista.append(Chip(ROTULOS[chave], valor, sem_o_valor(chave, valor)))

    for chave in ("referencia", "documento", "busca"):
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


def atalhos_de_periodo(sessao, filtro: Filtro, args) -> list[dict]:
    """Tudo, o último mês com lançamento, os últimos três meses e os dois anos."""
    from calendar import monthrange

    from sqlalchemy import func

    from app.formato import mes_curto

    def item(rotulo, inicio, fim):
        base = query_sem(args, "inicio", "fim", "pagina")
        if inicio:
            base.update(inicio=[inicio.isoformat()], fim=[fim.isoformat()])
        ativo = filtro.inicio == inicio and filtro.fim == fim
        return {"rotulo": rotulo, "args": base, "ativo": ativo}

    lista = [item("Tudo", None, None)]
    ultima = sessao.scalar(select(func.max(filtro.coluna_de_data))) if sessao else None
    if ultima is None:
        return lista

    fim_do_mes = date(ultima.year, ultima.month, monthrange(ultima.year, ultima.month)[1])
    if ultima.month > 2:
        ano, mes = ultima.year, ultima.month - 2
    else:
        ano, mes = ultima.year - 1, ultima.month + 10
    lista += [
        item(
            f"{mes_curto(ultima.month)}/{ultima.year}",
            date(ultima.year, ultima.month, 1),
            fim_do_mes,
        ),
        item("Últimos 3 meses", date(ano, mes, 1), fim_do_mes),
        item(str(ultima.year), date(ultima.year, 1, 1), date(ultima.year, 12, 31)),
        item(str(ultima.year - 1), date(ultima.year - 1, 1, 1), date(ultima.year - 1, 12, 31)),
    ]
    return lista


def alternar(args, chave: str, valor: str) -> dict:
    """A query string com `valor` posto em `chave`, ou tirado se já estava."""
    base = query_sem(args, "pagina")
    atuais = base.get(chave, [])
    novos = [v for v in atuais if v != valor] if valor in atuais else atuais + [valor]
    if novos:
        base[chave] = novos
    else:
        base.pop(chave, None)
    return base


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


def todos_os_valores(args) -> dict[str, list[str]]:
    """A query string como dict de listas; `**args` perderia os repetidos."""
    return {
        chave: [valor for valor in args.getlist(chave) if valor]
        for chave in args.keys()
        if any(valor for valor in args.getlist(chave))
    }


def query_sem(args, *remover: str) -> dict:
    """Copia da query string sem certas chaves — para montar links e formularios."""
    return {
        chave: valores for chave, valores in todos_os_valores(args).items() if chave not in remover
    }


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
