"""Usuario local.

Keycloak decide quem entra (grupo /apps/controle-despesa); o perfil aqui decide
o que a pessoa faz. Nao ha senha: `external_id` e o `sub` do Keycloak.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db

# Menor privilegio primeiro: a ordem define a hierarquia.
PERFIS = ("leitor", "operador", "admin")


class Usuario(db.Model):
    __tablename__ = "tb_usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    external_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )

    perfil: Mapped[str] = mapped_column(String(20), nullable=False, server_default="leitor")

    # Espelha o grupo no Keycloak. Perder o grupo desativa; nunca remove.
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ultimo_acesso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "perfil IN ('leitor', 'operador', 'admin')", name="ck_usuario_perfil"
        ),
    )

    @property
    def nivel(self) -> int:
        try:
            return PERFIS.index(self.perfil)
        except ValueError:
            return 0

    @property
    def pode_ler(self) -> bool:
        return self.ativo

    @property
    def pode_escrever(self) -> bool:
        """Importar planilha, lancar e editar despesa."""
        return self.ativo and self.nivel >= PERFIS.index("operador")

    @property
    def pode_administrar(self) -> bool:
        """Painel adm, backup, restauracao, limpeza e auditoria."""
        return self.ativo and self.nivel >= PERFIS.index("admin")

    def __repr__(self) -> str:
        return f"<Usuario {self.email} {self.perfil}>"
