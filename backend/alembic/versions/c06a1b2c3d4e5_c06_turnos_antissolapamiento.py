"""C-06 turnos anti-solapamiento (Migración 004)."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c06a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "c05a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
GUC = "current_setting('app.tenant_id')::uuid"


def upgrade() -> None:
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
    op.create_table(
        "turno",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("paciente_id", UUID, nullable=True),
        sa.Column("profesional_id", UUID, nullable=False),
        sa.Column("sillon_id", UUID, nullable=False),
        sa.Column("prestacion_id", UUID, nullable=False),
        sa.Column("inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fin", sa.DateTime(timezone=True), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default=sa.text("'pendiente'")),
        sa.Column("origen", sa.String(20), nullable=False, server_default=sa.text("'recepcion'")),
        sa.Column("token_portal", sa.String(64), nullable=True),
        sa.Column("sobreturno", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sena_id", UUID, nullable=True),
        sa.CheckConstraint("fin > inicio", name="turno_fin_despues_inicio"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], name="fk_turno_tenant_id_tenant", ondelete="RESTRICT"),

        sa.ForeignKeyConstraint(["profesional_id"], ["profesional.id"], name="fk_turno_profesional_id_profesional", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sillon_id"], ["sillon.id"], name="fk_turno_sillon_id_sillon", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["prestacion_id"], ["prestacion.id"], name="fk_turno_prestacion_id_prestacion", ondelete="RESTRICT"),
    )
    op.create_index("ix_turno_tenant_id", "turno", ["tenant_id"])
    op.create_index("ix_turno_profesional_id", "turno", ["profesional_id"])
    op.create_index("ix_turno_sillon_id", "turno", ["sillon_id"])
    # Exclusion constraints (RN-AG-01/02)
    op.execute(sa.text(
        "ALTER TABLE turno ADD CONSTRAINT excl_turno_profesional "
        "EXCLUDE USING gist (profesional_id WITH =, tstzrange(inicio, fin) WITH &&) "
        "WHERE (estado <> 'cancelado')"
    ))
    op.execute(sa.text(
        "ALTER TABLE turno ADD CONSTRAINT excl_turno_sillon "
        "EXCLUDE USING gist (sillon_id WITH =, tstzrange(inicio, fin) WITH &&) "
        "WHERE (estado <> 'cancelado')"
    ))
    # RLS
    op.execute(sa.text("ALTER TABLE turno ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE turno FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text(
        f"CREATE POLICY turno_isolation ON turno FOR ALL TO PUBLIC "
        f"USING (tenant_id = {GUC}) WITH CHECK (tenant_id = {GUC})"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS turno_isolation ON turno"))
    op.execute(sa.text("ALTER TABLE turno DROP CONSTRAINT IF EXISTS excl_turno_sillon"))
    op.execute(sa.text("ALTER TABLE turno DROP CONSTRAINT IF EXISTS excl_turno_profesional"))
    op.drop_index("ix_turno_sillon_id", table_name="turno")
    op.drop_index("ix_turno_profesional_id", table_name="turno")
    op.drop_index("ix_turno_tenant_id", table_name="turno")
    op.drop_table("turno")