"""C-10 cobros mercadopago (Migración)."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c10a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "c09a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
GUC = "current_setting('app.tenant_id')::uuid"


def upgrade() -> None:
    op.add_column("turno", sa.Column("mp_order_id", sa.String(64), nullable=True))

    op.create_table(
        "pago",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("turno_id", UUID, nullable=False),
        sa.Column("mp_payment_id", sa.String(64), nullable=True),
        sa.Column("mp_order_id", sa.String(64), nullable=True),
        sa.Column("monto", sa.Numeric(12, 2), nullable=False),
        sa.Column("moneda", sa.String(8), nullable=False, server_default=sa.text("'ARS'")),
        sa.Column("estado", sa.String(20), nullable=False, server_default=sa.text("'pendiente'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("acreditado_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], name="fk_pago_tenant_id_tenant", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["turno_id"], ["turno.id"], name="fk_pago_turno_id_turno", ondelete="CASCADE"),
        sa.UniqueConstraint("mp_payment_id", name="uq_pago_mp_payment_id"),
    )
    op.create_index("ix_pago_tenant_id", "pago", ["tenant_id"])
    op.create_index("ix_pago_turno_id", "pago", ["turno_id"])
    op.create_index("ix_pago_mp_order_id", "pago", ["mp_order_id"])
    # RLS
    op.execute(sa.text("ALTER TABLE pago ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE pago FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text(
        f"CREATE POLICY pago_isolation ON pago FOR ALL TO PUBLIC "
        f"USING (tenant_id = {GUC}) WITH CHECK (tenant_id = {GUC})"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS pago_isolation ON pago"))
    op.drop_index("ix_pago_mp_order_id", table_name="pago")
    op.drop_index("ix_pago_turno_id", table_name="pago")
    op.drop_index("ix_pago_tenant_id", table_name="pago")
    op.drop_table("pago")
    op.drop_column("turno", "mp_order_id")