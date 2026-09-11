"""Importacao: analisar (previa) e gravar.

A previa nao escreve nada. A gravacao acontece em uma transacao, e e idempotente
por `referencia`: reimportar o mesmo arquivo atualiza, nao duplica.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal
from io import BytesIO

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.auditoria.servico import registrar
from app.importacao.planilha import ErroLinha, LinhaPlanilha, chave_natural, ler
from app.models import CentroCusto, Despesa, Fornecedor, Importacao, Natureza


@dataclass
class Previa:
    arquivo: str
    sha256: str
    linhas: list[LinhaPlanilha] = field(default_factory=list)
    erros: list[ErroLinha] = field(default_factory=list)
    ignoradas: int = 0
    novos_fornecedores: list[str] = field(default_factory=list)
    novas_naturezas: list[str] = field(default_factory=list)
    novos_centros: list[str] = field(default_factory=list)
    a_criar: int = 0
    a_atualizar: int = 0
    divergentes: int = 0
    total_original: Decimal = Decimal("0.00")
    total_baixado: Decimal = Decimal("0.00")
    ja_importado: Importacao | None = None


def analisar(session, origem, *, arquivo_nome: str) -> Previa:
    if hasattr(origem, "read"):
        conteudo = origem.read()
    else:
        with open(origem, "rb") as arquivo:
            conteudo = arquivo.read()

    sha = hashlib.sha256(conteudo).hexdigest()
    resultado = ler(BytesIO(conteudo))
    linhas = resultado.linhas

    previa = Previa(
        arquivo=arquivo_nome,
        sha256=sha,
        linhas=linhas,
        erros=resultado.erros,
        ignoradas=resultado.ignoradas,
        divergentes=sum(1 for linha in linhas if linha.divergente),
        total_original=sum((linha.valor_original for linha in linhas), Decimal("0.00")),
        total_baixado=sum((linha.valor_baixado for linha in linhas), Decimal("0.00")),
        ja_importado=session.scalars(
            select(Importacao).where(Importacao.sha256 == sha).order_by(Importacao.id.desc())
        ).first(),
    )

    previa.novos_fornecedores = _inexistentes(
        session, Fornecedor, {linha.fornecedor for linha in linhas}
    )
    previa.novas_naturezas = _inexistentes(session, Natureza, {linha.natureza for linha in linhas})
    previa.novos_centros = _centros_inexistentes(session, {linha.centro_custo for linha in linhas})

    existentes = _chaves_existentes(session, linhas)
    previa.a_atualizar = sum(1 for linha in linhas if chave_natural(linha) in existentes)
    previa.a_criar = len(linhas) - previa.a_atualizar

    return previa


def gravar(session, previa: Previa, *, usuario=None, progresso=None) -> Importacao:
    """`progresso(feitas, total)` e chamado a cada lote, para a linha de comando
    nao ficar minutos em silencio numa planilha grande."""
    importacao = Importacao(
        arquivo=previa.arquivo,
        sha256=previa.sha256,
        usuario_id=usuario.id if usuario else None,
        linhas_lidas=len(previa.linhas),
        linhas_ignoradas=previa.ignoradas,
    )
    session.add(importacao)
    session.flush()

    # O dominio e resolvido ANTES do laco: obter_ou_criar consulta o banco, e uma
    # consulta no meio de uma despesa ainda incompleta dispararia o autoflush em
    # cima dela. De quebra, sao 3 selects no total em vez de 3 por linha.
    centros, fornecedores, naturezas = _resolver_dominio(session, previa.linhas)

    criados, atualizados = _gravar_em_lote(
        session,
        previa.linhas,
        importacao_id=importacao.id,
        centros=centros,
        fornecedores=fornecedores,
        naturezas=naturezas,
        usuario_id=usuario.id if usuario else None,
        progresso=progresso,
    )

    importacao.criados = criados
    importacao.atualizados = atualizados

    registrar(
        session,
        acao="importacao.gravar",
        usuario=usuario,
        alvo_tipo="importacao",
        alvo_id=importacao.id,
        payload={
            "arquivo": previa.arquivo,
            "criados": criados,
            "atualizados": atualizados,
            "ignoradas": previa.ignoradas,
            "erros": len(previa.erros),
            "divergentes": previa.divergentes,
            "total_baixado": str(previa.total_baixado),
        },
    )

    session.commit()
    return importacao


# N linhas x 12 colunas parametros; o teto do PostgreSQL e 65535.
LINHAS_POR_LOTE = 2_000

# Espelha o indice uq_despesa_natural. Mudar um, mudar o outro.
ALVO_DO_CONFLITO = (
    Despesa.referencia,
    Despesa.data_baixa,
    Despesa.fornecedor_id,
    Despesa.natureza_id,
    Despesa.centro_custo_id,
    Despesa.documento,
    func.md5(Despesa.historico),
)

# Atualizadas na reimportacao. `divergencia_ignorada` fica de fora de proposito:
# quem marcou "nao comparar" nao pode perder isso ao reimportar.
COLUNAS_DA_PLANILHA = (
    "data_emissao",
    "centro_custo_id",
    "fornecedor_id",
    "natureza_id",
    "historico",
    "documento",
    "valor_original",
    "valor_baixado",
    "importacao_id",
)


def _gravar_em_lote(
    session, linhas, *, importacao_id, centros, fornecedores, naturezas, usuario_id,
    progresso=None,
) -> tuple[int, int]:
    """Upsert em executemany. A contagem sai de consulta previa: um RETURNING
    por linha custava mais que a propria gravacao."""
    ja_existiam = _chaves_existentes(session, linhas)

    inserir = pg_insert(Despesa)
    comando = inserir.on_conflict_do_update(
        index_elements=ALVO_DO_CONFLITO,
        set_={
            **{coluna: getattr(inserir.excluded, coluna) for coluna in COLUNAS_DA_PLANILHA},
            "criado_por_id": func.coalesce(
                Despesa.criado_por_id, inserir.excluded.criado_por_id
            ),
            "atualizado_em": func.now(),
        },
    )

    for inicio in range(0, len(linhas), LINHAS_POR_LOTE):
        session.execute(
            comando,
            [
                {
                    "referencia": linha.referencia,
                    "data_baixa": linha.data_baixa,
                    "data_emissao": linha.data_emissao,
                    "centro_custo_id": centros[linha.centro_custo.upper()].id,
                    "fornecedor_id": fornecedores[linha.fornecedor.upper()].id,
                    "natureza_id": naturezas[linha.natureza.upper()].id,
                    "historico": linha.historico,
                    "documento": linha.documento,
                    "valor_original": linha.valor_original,
                    "valor_baixado": linha.valor_baixado,
                    "importacao_id": importacao_id,
                    "criado_por_id": usuario_id,
                }
                for linha in linhas[inicio : inicio + LINHAS_POR_LOTE]
            ],
        )
        if progresso is not None:
            progresso(min(inicio + LINHAS_POR_LOTE, len(linhas)), len(linhas))

    atualizados = sum(1 for linha in linhas if chave_natural(linha) in ja_existiam)
    return len(linhas) - atualizados, atualizados


def _resolver_dominio(session, linhas: list[LinhaPlanilha]) -> tuple[dict, dict, dict]:
    centros = {
        codigo.upper(): CentroCusto.obter_ou_criar(session, codigo)
        for codigo in sorted({linha.centro_custo for linha in linhas})
    }
    fornecedores = {
        nome.upper(): Fornecedor.obter_ou_criar(session, nome)
        for nome in sorted({linha.fornecedor for linha in linhas})
    }
    naturezas = {
        nome.upper(): Natureza.obter_ou_criar(session, nome)
        for nome in sorted({linha.natureza for linha in linhas})
    }
    session.flush()
    return centros, fornecedores, naturezas


def _inexistentes(session, modelo, nomes: set[str]) -> list[str]:
    nomes = {nome for nome in nomes if nome}
    if not nomes:
        return []
    ja_tem = {nome.upper() for nome in session.scalars(select(modelo.nome))}
    return sorted(nome for nome in nomes if nome.upper() not in ja_tem)


def _centros_inexistentes(session, codigos: set[str]) -> list[str]:
    codigos = {codigo for codigo in codigos if codigo}
    if not codigos:
        return []
    ja_tem = set(session.scalars(select(CentroCusto.codigo)))
    return sorted(codigo for codigo in codigos if codigo not in ja_tem)


# O IN gasta um parametro por referencia; acima de 65535 o comando falha.
LOTE_DE_PARAMETROS = 10_000


def _chaves_existentes(session, linhas: list[LinhaPlanilha]) -> set[tuple]:
    """Contar so por referencia erraria: a mesma com outro fornecedor e nova."""
    referencias = sorted({linha.referencia for linha in linhas})
    if not referencias:
        return set()

    consulta = (
        select(
            Despesa.referencia,
            Despesa.data_baixa,
            func.upper(Fornecedor.nome),
            func.upper(Natureza.nome),
            CentroCusto.codigo,
            Despesa.documento,
            Despesa.historico,
        )
        .join(Fornecedor, Despesa.fornecedor_id == Fornecedor.id)
        .join(Natureza, Despesa.natureza_id == Natureza.id)
        .join(CentroCusto, Despesa.centro_custo_id == CentroCusto.id)
    )

    achadas: set[tuple] = set()
    for inicio in range(0, len(referencias), LOTE_DE_PARAMETROS):
        fatia = referencias[inicio : inicio + LOTE_DE_PARAMETROS]
        achadas.update(
            tuple(linha) for linha in session.execute(consulta.where(Despesa.referencia.in_(fatia)))
        )
    return achadas
