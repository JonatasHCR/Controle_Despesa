"""Backup, restauracao e limpeza — as operacoes do painel administrativo.

O pg_dump/pg_restore roda DENTRO deste container. Um sidecar precisaria do
socket do Docker, e ai qualquer falha da aplicacao viraria poder de criar
container na maquina.
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from sqlalchemy import delete, func, select

from app.despesas.filtros import Filtro
from app.models import Auditoria, Despesa, Fornecedor, Importacao, Natureza

# Fecha o path traversal: o nome vem da tela, e "../../etc/passwd" nao pode
# virar caminho. O regex e a primeira barreira; a segunda e conferir o pai.
NOME_VALIDO = re.compile(r"^[A-Za-z0-9._-]+\.(dump|sql\.gz|sql)$")

PALAVRA_LIMPAR = "LIMPAR"
PALAVRA_RESTAURAR = "RESTAURAR"

# tb_usuarios NUNCA e alvo: despesas e auditoria apontam para ele.
ALVOS = {
    "despesas": "Despesas (mantém fornecedores, naturezas e centros)",
    "importacoes": "Histórico de importações",
    "auditoria": "Trilha de auditoria",
    "dominio": "Fornecedores e naturezas sem uso",
}


class ErroDeManutencao(Exception):
    pass


def _conexao() -> dict:
    """Parametros do banco que o app esta usando de fato.

    Derivados da URI do SQLAlchemy, e nao lidos do ambiente: assim o backup
    acompanha o banco da configuracao corrente — inclusive o de teste.
    """
    from flask import current_app

    partes = urlsplit(current_app.config["SQLALCHEMY_DATABASE_URI"])
    return {
        "host": partes.hostname or "db",
        "porta": str(partes.port or 5432),
        "usuario": unquote(partes.username or ""),
        "senha": unquote(partes.password or ""),
        "banco": (partes.path or "/").lstrip("/"),
    }


def diretorio() -> Path:
    from flask import current_app

    caminho = Path(current_app.config["BACKUP_DIR"])
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


def listar_backups() -> list[dict]:
    arquivos = []
    for arquivo in diretorio().iterdir():
        if not arquivo.is_file() or not NOME_VALIDO.match(arquivo.name):
            continue
        info = arquivo.stat()
        arquivos.append(
            {
                "nome": arquivo.name,
                "bytes": info.st_size,
                "criado_em": datetime.fromtimestamp(info.st_mtime),
            }
        )
    return sorted(arquivos, key=lambda item: item["criado_em"], reverse=True)


def resolver_arquivo(nome: str) -> Path:
    if not NOME_VALIDO.match(nome or ""):
        raise ErroDeManutencao("nome de arquivo inválido")
    alvo = (diretorio() / nome).resolve()
    if alvo.parent != diretorio().resolve():
        raise ErroDeManutencao("nome de arquivo inválido")
    if not alvo.is_file():
        raise ErroDeManutencao("arquivo não encontrado")
    return alvo


def gerar_backup() -> Path:
    conexao = _conexao()
    destino = diretorio() / f"controle_despesa_{datetime.now():%Y%m%d_%H%M%S}.dump"
    comando = [
        "pg_dump",
        "-h", conexao["host"],
        "-p", conexao["porta"],
        "-U", conexao["usuario"],
        "-Fc",
        "--no-owner",
        "--no-privileges",
        "-f", str(destino),
        conexao["banco"],
    ]
    resultado = _rodar(comando, conexao)
    if resultado.returncode != 0 or not destino.exists():
        destino.unlink(missing_ok=True)
        raise ErroDeManutencao(f"pg_dump falhou: {resultado.stderr.strip()[:400]}")
    return destino


def restaurar(session, nome: str) -> str:
    arquivo = resolver_arquivo(nome)

    # A conexao aberta trava contra os DROPs da restauracao.
    session.close()

    conexao = _conexao()
    if arquivo.name.endswith(".dump"):
        comando = [
            "pg_restore",
            "-h", conexao["host"],
            "-p", conexao["porta"],
            "-U", conexao["usuario"],
            "-d", conexao["banco"],
            "--clean", "--if-exists", "--no-owner", "--no-privileges",
            str(arquivo),
        ]
    else:
        _exigir_clean(arquivo)
        comando = [
            "psql",
            "-h", conexao["host"],
            "-p", conexao["porta"],
            "-U", conexao["usuario"],
            "-d", conexao["banco"],
            "--set", "ON_ERROR_STOP=1",
            "--single-transaction",
            "-f", str(arquivo),
        ]

    resultado = _rodar(comando, conexao)
    if resultado.returncode != 0:
        problemas = _erros_relevantes(resultado.stderr)
        if problemas:
            raise ErroDeManutencao("restauração falhou: " + problemas[0][:400])
    return arquivo.name


def contar(session, alvo: str, filtro: Filtro | None = None) -> int:
    """Dry-run da limpeza: quantos registros o filtro pega."""
    if alvo not in ALVOS:
        raise ErroDeManutencao(f"alvo desconhecido: {alvo}")

    if alvo == "despesas":
        from app.despesas.filtros import aplicar

        consulta = aplicar(select(func.count(Despesa.id)), filtro or Filtro())
        return session.scalar(consulta.order_by(None)) or 0
    if alvo == "importacoes":
        return session.scalar(select(func.count(Importacao.id))) or 0
    if alvo == "auditoria":
        return session.scalar(select(func.count(Auditoria.id))) or 0
    return len(_dominio_sem_uso(session))


def limpar(session, alvo: str, filtro: Filtro | None = None) -> int:
    if alvo not in ALVOS:
        raise ErroDeManutencao(f"alvo desconhecido: {alvo}")

    if alvo == "despesas":
        from app.despesas.filtros import aplicar

        ids = session.scalars(aplicar(select(Despesa.id), filtro or Filtro())).all()
        if not ids:
            return 0
        session.execute(delete(Despesa).where(Despesa.id.in_(ids)))
        return len(ids)

    if alvo == "importacoes":
        # As despesas ficam; perdem so o vinculo com o lote (FK SET NULL).
        quantidade = session.scalar(select(func.count(Importacao.id))) or 0
        session.execute(delete(Importacao))
        return quantidade

    if alvo == "auditoria":
        quantidade = session.scalar(select(func.count(Auditoria.id))) or 0
        session.execute(delete(Auditoria))
        return quantidade

    orfaos = _dominio_sem_uso(session)
    for modelo, identificador in orfaos:
        session.execute(delete(modelo).where(modelo.id == identificador))
    return len(orfaos)


def _dominio_sem_uso(session) -> list[tuple]:
    usados_fornecedor = select(Despesa.fornecedor_id).distinct()
    usados_natureza = select(Despesa.natureza_id).distinct()
    achados = []
    for identificador in session.scalars(
        select(Fornecedor.id).where(Fornecedor.id.not_in(usados_fornecedor))
    ):
        achados.append((Fornecedor, identificador))
    for identificador in session.scalars(
        select(Natureza.id).where(Natureza.id.not_in(usados_natureza))
    ):
        achados.append((Natureza, identificador))
    return achados


def _exigir_clean(arquivo: Path) -> None:
    """Um dump .sql sem DROP restaurado por cima de um banco povoado aplica so
    os COPY que nao conflitam, e deixa o banco num estado misturado."""
    with arquivo.open("r", encoding="utf-8", errors="ignore") as conteudo:
        for linha in conteudo:
            if linha.startswith("DROP "):
                return
    raise ErroDeManutencao(
        f"{arquivo.name} não tem comandos DROP; restaurar assim mistura os dados "
        "atuais com os do backup. Gere o dump com --clean --if-exists."
    )


def _erros_relevantes(saida: str) -> list[str]:
    tolerados = ('unrecognized configuration parameter "transaction_timeout"',)
    return [
        linha
        for linha in saida.splitlines()
        if "error" in linha.lower() and not any(item in linha for item in tolerados)
    ]


def _rodar(comando: list[str], conexao: dict) -> subprocess.CompletedProcess:
    ambiente = dict(os.environ, PGPASSWORD=conexao["senha"])
    # Lista, nunca shell=True: nada aqui passa por interpretador de comando.
    return subprocess.run(comando, capture_output=True, text=True, env=ambiente, timeout=600)
