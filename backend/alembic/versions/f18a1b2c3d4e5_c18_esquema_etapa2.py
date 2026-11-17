"""C-18 reserve a minimal tenant-scoped schema for post-MVP (Migration 012)."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f18a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "e17a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
GUC = "current_setting('app.tenant_id')::uuid"


def _tenant_rls(table: str) -> None:
    op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text(
        f"CREATE POLICY {table}_isolation ON {table} FOR ALL TO PUBLIC "
        f"USING (tenant_id = {GUC}) WITH CHECK (tenant_id = {GUC})"
    ))


def upgrade() -> None:
    # paciente.obra_social already exists since C-12 migration 008. Do not add it again.
    op.create_table(
        "nomenclador",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("codigo", sa.String(48), nullable=False),
        sa.Column("descripcion", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "codigo", name="uq_nomenclador_tenant_codigo"),
    )
    op.create_index("ix_nomenclador_tenant_id", "nomenclador", ["tenant_id"])
    _tenant_rls("nomenclador")

    op.create_table(
        "comprobante_fiscal",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("estado", sa.String(16), nullable=False, server_default=sa.text("'reservado'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("estado = 'reservado'", name="comprobante_fiscal_stub_estado"),
    )
    op.create_index("ix_comprobante_fiscal_tenant_id", "comprobante_fiscal", ["tenant_id"])
    _tenant_rls("comprobante_fiscal")


def downgrade() -> None:
    for table in ("comprobante_fiscal", "nomenclador"):
        op.execute(sa.text(f"DROP POLICY IF EXISTS {table}_isolation ON {table}"))
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_table(table)
