"""C-09 lista de espera (Migración 005)."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c09a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "c06a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
GUC = "current_setting('app.tenant_id')::uuid"


def upgrade() -> None:
    op.create_table(
        "lista_espera",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("paciente_id", UUID, nullable=True),
        sa.Column("prestacion_id", UUID, nullable=False),
        sa.Column("profesional_id", UUID, nullable=True),
        sa.Column("franja", sa.String(20), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default=sa.text("'activa'")),
        sa.Column("ofrecida_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], name="fk_lista_espera_tenant_id_tenant", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["prestacion_id"], ["prestacion.id"], name="fk_lista_espera_prestacion_id_prestacion", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["profesional_id"], ["profesional.id"], name="fk_lista_espera_profesional_id_profesional", ondelete="SET NULL"),
    )
    op.create_index("ix_lista_espera_tenant_id", "lista_espera", ["tenant_id"])
    op.create_index("ix_lista_espera_prestacion_id", "lista_espera", ["prestacion_id"])
    op.create_index("ix_lista_espera_profesional_id", "lista_espera", ["profesional_id"])
    # RLS
    op.execute(sa.text("ALTER TABLE lista_espera ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE lista_espera FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text(
        f"CREATE POLICY lista_espera_isolation ON lista_espera FOR ALL TO PUBLIC "
        f"USING (tenant_id = {GUC}) WITH CHECK (tenant_id = {GUC})"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS lista_espera_isolation ON lista_espera"))
    op.drop_index("ix_lista_espera_profesional_id", table_name="lista_espera")
    op.drop_index("ix_lista_espera_prestacion_id", table_name="lista_espera")
    op.drop_index("ix_lista_espera_tenant_id", table_name="lista_espera")
    op.drop_table("lista_espera")