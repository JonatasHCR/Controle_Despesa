"""Importacao: analisar (previa) e gravar.

A previa nao escreve nada. A gravacao acontece em uma transacao, e e idempotente
por `referencia`: reimportar o mesmo arquivo atualiza, nao duplica.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal
from io import BytesIO

from sqlalchemy import select

from app.auditoria.servico import registrar
from app.importacao.planilha import ErroLinha, LinhaPlanilha, ler
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

    existentes = _referencias_existentes(session, [linha.referencia for linha in linhas])
    previa.a_atualizar = sum(1 for linha in linhas if linha.referencia in existentes)
    previa.a_criar = len(linhas) - previa.a_atualizar

    return previa


def gravar(session, previa: Previa, *, usuario=None) -> Importacao:
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

    existentes = {
        despesa.referencia: despesa
        for despesa in session.scalars(
            select(Despesa).where(
                Despesa.referencia.in_([linha.referencia for linha in previa.linhas] or [0])
            )
        )
    }

    criados = atualizados = 0
    for linha in previa.linhas:
        despesa = existentes.get(linha.referencia)
        if despesa is None:
            despesa = Despesa(referencia=linha.referencia)
            criados += 1
        else:
            atualizados += 1

        despesa.data_baixa = linha.data_baixa
        despesa.data_emissao = linha.data_emissao
        despesa.centro_custo = centros[linha.centro_custo.upper()]
        despesa.fornecedor = fornecedores[linha.fornecedor.upper()]
        despesa.natureza = naturezas[linha.natureza.upper()]
        despesa.historico = linha.historico
        despesa.documento = linha.documento
        despesa.valor_original = linha.valor_original
        despesa.valor_baixado = linha.valor_baixado
        despesa.importacao_id = importacao.id
        if despesa.criado_por_id is None and usuario is not None:
            despesa.criado_por_id = usuario.id

        session.add(despesa)

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


def _referencias_existentes(session, referencias: list[int]) -> set[int]:
    if not referencias:
        return set()
    return set(
        session.scalars(select(Despesa.referencia).where(Despesa.referencia.in_(referencias)))
    )
