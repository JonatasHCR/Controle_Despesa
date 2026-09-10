"""Painel administrativo: backup, limpeza, restauracao e perfis."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.admin import manutencao
from app.models import Auditoria, Despesa, Fornecedor, Importacao, Usuario

pytestmark = pytest.mark.integration


@pytest.fixture
def backups(app, tmp_path):
    """Diretorio de backup isolado por teste."""
    anterior = app.config["BACKUP_DIR"]
    app.config["BACKUP_DIR"] = str(tmp_path)
    yield tmp_path
    app.config["BACKUP_DIR"] = anterior


# --- nomes de arquivo: a barreira contra path traversal --------------------


@pytest.mark.parametrize(
    "nome",
    [
        "../../etc/passwd",
        "..%2Fescapou.dump",
        "/etc/shadow",
        "backup.dump/../../fora.dump",
        "sem_extensao",
        "malicioso.sh",
        "",
    ],
)
def test_nome_de_arquivo_perigoso_e_recusado(app, backups, nome):
    with app.app_context(), pytest.raises(manutencao.ErroDeManutencao):
        manutencao.resolver_arquivo(nome)


def test_arquivo_valido_mas_inexistente_tambem_e_recusado(app, backups):
    with app.app_context(), pytest.raises(manutencao.ErroDeManutencao, match="não encontrado"):
        manutencao.resolver_arquivo("nao_existe.dump")


def test_arquivo_legitimo_resolve(app, backups):
    (backups / "controle_despesa_20260909_120000.dump").write_bytes(b"conteudo")
    with app.app_context():
        achado = manutencao.resolver_arquivo("controle_despesa_20260909_120000.dump")
    assert achado.parent == backups


def test_listagem_ignora_arquivo_que_nao_e_backup(app, backups):
    (backups / "bom.dump").write_bytes(b"x")
    (backups / "README.txt").write_text("nada a ver")
    (backups / "script.sh").write_text("rm -rf /")
    with app.app_context():
        nomes = [item["nome"] for item in manutencao.listar_backups()]
    assert nomes == ["bom.dump"]


# --- backup de verdade ------------------------------------------------------


def test_backup_gera_arquivo_com_conteudo(entrar, admin, carregado, backups):
    resposta = entrar(admin).post("/administracao/backups", follow_redirects=True)
    assert resposta.status_code == 200
    arquivos = list(backups.glob("*.dump"))
    assert len(arquivos) == 1
    assert arquivos[0].stat().st_size > 1000


def test_backup_e_auditado(entrar, admin, carregado, backups, db):
    entrar(admin).post("/administracao/backups", follow_redirects=True)
    entrada = db.session.scalars(
        select(Auditoria).where(Auditoria.acao == "manutencao.backup")
    ).one()
    assert entrada.usuario_id == admin.id
    assert entrada.payload["bytes"] > 0


def test_backup_pode_ser_baixado(entrar, admin, carregado, backups):
    cliente = entrar(admin)
    cliente.post("/administracao/backups", follow_redirects=True)
    nome = next(backups.glob("*.dump")).name
    resposta = cliente.get(f"/administracao/backups/{nome}")
    assert resposta.status_code == 200
    assert "attachment" in resposta.headers["Content-Disposition"]


def test_download_de_caminho_forjado_nao_vaza_arquivo(entrar, admin, backups):
    resposta = entrar(admin).get("/administracao/backups/..%2F..%2Fetc%2Fpasswd")
    assert resposta.status_code in (302, 404)


def test_operador_nao_gera_backup(entrar, operador, backups):
    assert entrar(operador).post("/administracao/backups").status_code == 403


# --- contagem (dry-run) -----------------------------------------------------


def test_contagem_nao_apaga_nada(entrar, admin, carregado, db):
    resposta = entrar(admin).post(
        "/administracao/contagem", data={"alvo": "despesas"}
    )
    assert "127" in resposta.get_data(as_text=True)
    assert db.session.scalar(select(func.count()).select_from(Despesa)) == 127


def test_contagem_respeita_o_filtro(entrar, admin, carregado):
    resposta = entrar(admin).post(
        "/administracao/contagem", data={"alvo": "despesas", "natureza": "COMBUSTIVEL"}
    )
    assert ">5<" in resposta.get_data(as_text=True) or "5 " in resposta.get_data(as_text=True)


def test_contagem_de_alvo_desconhecido_e_recusada(entrar, admin):
    resposta = entrar(admin).post("/administracao/contagem", data={"alvo": "usuarios"})
    assert resposta.status_code == 400


# --- limpeza ----------------------------------------------------------------


def test_limpeza_sem_a_palavra_nao_apaga(entrar, admin, carregado, db):
    entrar(admin).post(
        "/administracao/limpeza",
        data={"alvo": "despesas", "confirmacao": "sim"},
        follow_redirects=True,
    )
    assert db.session.scalar(select(func.count()).select_from(Despesa)) == 127


def test_limpeza_com_a_palavra_apaga(entrar, admin, carregado, db):
    entrar(admin).post(
        "/administracao/limpeza",
        data={"alvo": "despesas", "confirmacao": "LIMPAR"},
        follow_redirects=True,
    )
    assert db.session.scalar(select(func.count()).select_from(Despesa)) == 0


def test_limpeza_filtrada_apaga_so_o_recorte(entrar, admin, carregado, db):
    entrar(admin).post(
        "/administracao/limpeza",
        data={"alvo": "despesas", "natureza": "COMBUSTIVEL", "confirmacao": "LIMPAR"},
        follow_redirects=True,
    )
    assert db.session.scalar(select(func.count()).select_from(Despesa)) == 122


def test_limpeza_de_despesas_preserva_o_dominio(entrar, admin, carregado, db):
    """Apagar lancamento nao pode levar junto a tabela de fornecedores."""
    entrar(admin).post(
        "/administracao/limpeza",
        data={"alvo": "despesas", "confirmacao": "LIMPAR"},
        follow_redirects=True,
    )
    assert db.session.scalar(select(func.count()).select_from(Fornecedor)) == 33


def test_limpeza_nunca_toca_em_usuarios(entrar, admin, carregado, db):
    quantos = db.session.scalar(select(func.count()).select_from(Usuario))
    for alvo in manutencao.ALVOS:
        entrar(admin).post(
            "/administracao/limpeza",
            data={"alvo": alvo, "confirmacao": "LIMPAR"},
            follow_redirects=True,
        )
    assert db.session.scalar(select(func.count()).select_from(Usuario)) == quantos


def test_apagar_importacoes_mantem_as_despesas(entrar, admin, carregado, db):
    entrar(admin).post(
        "/administracao/limpeza",
        data={"alvo": "importacoes", "confirmacao": "LIMPAR"},
        follow_redirects=True,
    )
    assert db.session.scalar(select(func.count()).select_from(Importacao)) == 0
    assert db.session.scalar(select(func.count()).select_from(Despesa)) == 127


def test_limpeza_e_auditada(entrar, admin, carregado, db):
    entrar(admin).post(
        "/administracao/limpeza",
        data={"alvo": "despesas", "confirmacao": "LIMPAR"},
        follow_redirects=True,
    )
    entrada = db.session.scalars(
        select(Auditoria).where(Auditoria.acao == "manutencao.limpeza")
    ).one()
    assert entrada.payload["removidos"] == 127


def test_operador_nao_limpa(entrar, operador, carregado, db):
    resposta = entrar(operador).post(
        "/administracao/limpeza", data={"alvo": "despesas", "confirmacao": "LIMPAR"}
    )
    assert resposta.status_code == 403
    assert db.session.scalar(select(func.count()).select_from(Despesa)) == 127


# --- restauracao ------------------------------------------------------------


def test_restauracao_sem_a_palavra_nao_roda(entrar, admin, carregado, backups, db):
    cliente = entrar(admin)
    cliente.post("/administracao/backups", follow_redirects=True)
    nome = next(backups.glob("*.dump")).name

    cliente.post(
        "/administracao/limpeza",
        data={"alvo": "despesas", "confirmacao": "LIMPAR"},
        follow_redirects=True,
    )
    cliente.post(
        "/administracao/restauracao",
        data={"arquivo": nome, "confirmacao": "por favor"},
        follow_redirects=True,
    )
    assert db.session.scalar(select(func.count()).select_from(Despesa)) == 0


def test_dump_sql_sem_drop_e_recusado(app, backups):
    """Restaurar um .sql sem DROP por cima de um banco povoado mistura os dados."""
    arquivo = backups / "sem_clean.sql"
    arquivo.write_text("INSERT INTO tb_despesas VALUES (1);\n")
    with app.app_context(), pytest.raises(manutencao.ErroDeManutencao, match="DROP"):
        manutencao._exigir_clean(arquivo)


def test_dump_sql_com_drop_passa(app, backups):
    arquivo = backups / "com_clean.sql"
    arquivo.write_text("DROP TABLE IF EXISTS tb_despesas;\nCREATE TABLE tb_despesas ();\n")
    with app.app_context():
        manutencao._exigir_clean(arquivo)  # nao levanta


# --- perfis -----------------------------------------------------------------


def test_admin_promove_alguem(entrar, admin, leitor, db):
    entrar(admin).post(
        f"/administracao/pessoas/{leitor.id}/perfil",
        data={"perfil": "operador"},
        follow_redirects=True,
    )
    db.session.refresh(leitor)
    assert leitor.perfil == "operador"


def test_mudanca_de_perfil_e_auditada(entrar, admin, leitor, db):
    entrar(admin).post(
        f"/administracao/pessoas/{leitor.id}/perfil",
        data={"perfil": "admin"},
        follow_redirects=True,
    )
    entrada = db.session.scalars(
        select(Auditoria).where(Auditoria.acao == "usuario.perfil")
    ).one()
    assert entrada.payload["de"] == "leitor"
    assert entrada.payload["para"] == "admin"


def test_admin_nao_rebaixa_a_si_mesmo(entrar, admin, db):
    """Senao o ultimo admin se tranca do lado de fora."""
    entrar(admin).post(
        f"/administracao/pessoas/{admin.id}/perfil",
        data={"perfil": "leitor"},
        follow_redirects=True,
    )
    db.session.refresh(admin)
    assert admin.perfil == "admin"


def test_perfil_inventado_e_recusado(entrar, admin, leitor, db):
    entrar(admin).post(
        f"/administracao/pessoas/{leitor.id}/perfil",
        data={"perfil": "superusuario"},
        follow_redirects=True,
    )
    db.session.refresh(leitor)
    assert leitor.perfil == "leitor"


def test_operador_nao_muda_perfil(entrar, operador, leitor, db):
    resposta = entrar(operador).post(
        f"/administracao/pessoas/{leitor.id}/perfil", data={"perfil": "admin"}
    )
    assert resposta.status_code == 403
    db.session.refresh(leitor)
    assert leitor.perfil == "leitor"


# --- auditoria (leitura) ----------------------------------------------------


def test_auditoria_lista_o_que_aconteceu(entrar, admin, carregado, db):
    from app.auditoria.servico import registrar

    registrar(db.session, acao="despesa.criar", usuario=admin, alvo_tipo="despesa", alvo_id=1)
    db.session.commit()

    corpo = entrar(admin).get("/auditoria/").get_data(as_text=True)
    assert "despesa.criar" in corpo
    assert admin.nome in corpo


def test_auditoria_filtra_por_acao(entrar, admin, db):
    from app.auditoria.servico import registrar

    registrar(db.session, acao="despesa.criar", usuario=admin, alvo_tipo="despesa")
    registrar(db.session, acao="despesa.excluir", usuario=admin, alvo_tipo="despesa")
    db.session.commit()

    corpo = entrar(admin).get("/auditoria/?acao=despesa.criar").get_data(as_text=True)
    # A celula da tabela, e nao a pagina toda: o combo de filtro lista as duas
    # acoes de qualquer jeito.
    assert "<td>despesa.criar</td>" in corpo
    assert "<td>despesa.excluir</td>" not in corpo


# --- XSS refletido ----------------------------------------------------------


def carga_maliciosa() -> str:
    return "<script>alert(document.cookie)</script>"


def com_token(cliente):
    """O token CSRF que o navegador do próprio admin teria."""
    import re

    pagina = cliente.get("/administracao/").get_data(as_text=True)
    achado = re.search(r'name="csrf_token" value="([^"]+)"', pagina)
    return achado.group(1) if achado else ""


def test_alvo_invalido_nao_volta_cru_para_o_html(entrar, admin, carregado):
    """Regressão: o `alvo` era interpolado numa f-string e voltava sem escapar."""
    cliente = entrar(admin)
    carga = carga_maliciosa()
    resposta = cliente.post(
        "/administracao/contagem",
        data={"alvo": carga, "csrf_token": com_token(cliente)},
    )
    corpo = resposta.get_data(as_text=True)
    assert resposta.status_code == 400
    assert carga not in corpo, "a carga voltou crua"
    assert "&lt;script&gt;" in corpo, "deveria estar escapada, e aparecer como texto"


def test_nenhuma_rota_monta_html_com_f_string():
    """A f-string com HTML é o padrão que produziu o buraco; não deve voltar."""
    import re
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent.parent / "app"
    # Uma tag de verdade: `class=`, `</` ou `/>`. O `<Despesa ...>` dos __repr__
    # também começa com `<`, e não é HTML.
    tag = re.compile(r"""f['"][^'"]*<[a-zA-Z][^'"]*(class=|</|/>)""")
    suspeitas = []
    for arquivo in raiz.rglob("*.py"):
        if arquivo.name == "svg.py":
            continue  # gera SVG e escapa cada valor com html.escape
        for numero, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
            if tag.search(linha):
                suspeitas.append(f"{arquivo.relative_to(raiz)}:{numero}")
    assert not suspeitas, "HTML montado em f-string: " + ", ".join(suspeitas)
