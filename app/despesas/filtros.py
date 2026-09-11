"""Motor de filtro, totais e agrupamento.

Um so lugar alimenta a tela, o XLSX e o PDF: relatorio que filtra diferente da
tela e relatorio que ninguem confere.

Os totais sao sempre SUM() sobre o filtro corrente — nenhum vem da planilha.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, String, cast, func, or_, select

from app.models import CentroCusto, Despesa, Fornecedor, Natureza

CAMPOS_DE_DATA = {"data_baixa", "data_emissao"}

ORDENS = {
    "data": Despesa.data_baixa,
    "emissao": Despesa.data_emissao,
    "valor": Despesa.valor_baixado,
    "referencia": Despesa.referencia,
    "documento": Despesa.documento,
}

AGRUPAMENTOS = ("natureza", "fornecedor", "centro", "ano", "mes", "dia")

ZERO = Decimal("0.00")


@dataclass
class Filtro:
    inicio: date | None = None
    fim: date | None = None
    campo_data: str = "data_baixa"
    centros: list[str] = field(default_factory=list)
    naturezas: list[str] = field(default_factory=list)
    fornecedores: list[str] = field(default_factory=list)
    documento: str = ""
    # Termo, e nao inteiro: quem lembra so do comeco do numero tambem acha.
    referencia: str | int | None = None
    busca: str = ""
    valor_minimo: Decimal | None = None
    valor_maximo: Decimal | None = None
    somente_divergentes: bool = False
    ordem: str = "data"
    decrescente: bool = False

    @property
    def coluna_de_data(self):
        if self.campo_data not in CAMPOS_DE_DATA:
            raise ValueError(f"campo de data desconhecido: {self.campo_data!r}")
        return getattr(Despesa, self.campo_data)


@dataclass
class Resumo:
    lancamentos: int = 0
    total_baixado: Decimal = ZERO
    total_original: Decimal = ZERO
    fornecedores: int = 0
    divergentes: int = 0


@dataclass
class LinhaAgrupada:
    rotulo: str
    quantidade: int
    total: Decimal


def aplicar(consulta: Select, filtro: Filtro) -> Select:
    consulta = _condicoes(consulta, filtro)

    if filtro.ordem not in ORDENS:
        raise ValueError(f"campo de ordenacao desconhecido: {filtro.ordem!r}")
    coluna = ORDENS[filtro.ordem]
    return consulta.order_by(coluna.desc() if filtro.decrescente else coluna.asc())


def totais(session, filtro: Filtro) -> Resumo:
    consulta = _condicoes(
        select(
            func.count(Despesa.id),
            func.coalesce(func.sum(Despesa.valor_baixado), ZERO),
            func.coalesce(func.sum(Despesa.valor_original), ZERO),
            func.count(func.distinct(Despesa.fornecedor_id)),
            func.count(Despesa.id).filter(Despesa.divergente),
        ),
        filtro,
    )
    quantidade, baixado, original, fornecedores, divergentes = session.execute(consulta).one()
    return Resumo(
        lancamentos=quantidade,
        total_baixado=baixado,
        total_original=original,
        fornecedores=fornecedores,
        divergentes=divergentes,
    )


def agrupar(session, filtro: Filtro, *, por: str) -> list[LinhaAgrupada]:
    if por not in AGRUPAMENTOS:
        raise ValueError(f"agrupamento desconhecido: {por!r}")

    rotulo, juncao, cronologico = _eixo(por, filtro)

    consulta = select(
        rotulo.label("rotulo"),
        func.count(Despesa.id).label("quantidade"),
        func.coalesce(func.sum(Despesa.valor_baixado), ZERO).label("total"),
    )
    if juncao is not None:
        consulta = consulta.join(juncao)
    consulta = _condicoes(consulta, filtro).group_by(rotulo)

    # Serie temporal sai em ordem de tempo; o resto, do maior para o menor.
    consulta = consulta.order_by(
        rotulo.asc() if cronologico else func.sum(Despesa.valor_baixado).desc()
    )

    return [
        LinhaAgrupada(rotulo=linha.rotulo, quantidade=linha.quantidade, total=linha.total)
        for linha in session.execute(consulta)
    ]


def _eixo(por: str, filtro: Filtro):
    """Devolve (expressao do rotulo, tabela a juntar, e se e cronologico)."""
    if por == "natureza":
        return Natureza.nome, Despesa.natureza, False
    if por == "fornecedor":
        return Fornecedor.nome, Despesa.fornecedor, False
    if por == "centro":
        return CentroCusto.codigo, Despesa.centro_custo, False
    if por == "ano":
        return func.to_char(filtro.coluna_de_data, "YYYY"), None, True
    if por == "mes":
        return func.to_char(filtro.coluna_de_data, "MM/YYYY"), None, True
    return func.to_char(filtro.coluna_de_data, "DD/MM/YYYY"), None, True


def _condicoes(consulta: Select, filtro: Filtro) -> Select:
    coluna_data = filtro.coluna_de_data

    if filtro.inicio:
        consulta = consulta.where(coluna_data >= filtro.inicio)
    if filtro.fim:
        consulta = consulta.where(coluna_data <= filtro.fim)

    if filtro.centros:
        consulta = consulta.where(
            Despesa.centro_custo_id.in_(
                select(CentroCusto.id).where(CentroCusto.codigo.in_(filtro.centros))
            )
        )
    if filtro.naturezas:
        # Igualdade, nao prefixo: 'SERVICOS DE ORCAMENTO' nao pode arrastar
        # 'SERVICOS DIVERSOS'.
        consulta = consulta.where(
            Despesa.natureza_id.in_(
                select(Natureza.id).where(Natureza.nome.in_(filtro.naturezas))
            )
        )
    if filtro.fornecedores:
        consulta = consulta.where(
            Despesa.fornecedor_id.in_(
                select(Fornecedor.id).where(Fornecedor.nome.in_(filtro.fornecedores))
            )
        )

    if filtro.documento:
        consulta = consulta.where(Despesa.documento.ilike(curinga(filtro.documento), escape="\\"))
    if filtro.referencia not in (None, ""):
        consulta = consulta.where(_como_texto(Despesa.referencia).like(curinga(filtro.referencia)))

    if filtro.busca:
        alvo = curinga(filtro.busca)
        # A referencia entra na busca livre: e o numero que a pessoa tem em maos,
        # e o lugar natural de digita-lo e a caixa de busca.
        consulta = consulta.where(
            or_(
                Despesa.historico.ilike(alvo, escape="\\"),
                Despesa.documento.ilike(alvo, escape="\\"),
                _como_texto(Despesa.referencia).like(alvo),
                Despesa.fornecedor_id.in_(
                    select(Fornecedor.id).where(Fornecedor.nome.ilike(alvo, escape="\\"))
                ),
            )
        )

    if filtro.valor_minimo is not None:
        consulta = consulta.where(Despesa.valor_baixado >= filtro.valor_minimo)
    if filtro.valor_maximo is not None:
        consulta = consulta.where(Despesa.valor_baixado <= filtro.valor_maximo)

    if filtro.somente_divergentes:
        consulta = consulta.where(Despesa.divergente)

    return consulta


def _como_texto(coluna):
    """A referencia e Integer; comparar por pedaco exige o cast."""
    return cast(coluna, String)


def curinga(termo: str) -> str:
    """Escapa os curingas do LIKE. Sem isto, buscar '%' traria a base inteira."""
    limpo = str(termo).strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{limpo}%"
