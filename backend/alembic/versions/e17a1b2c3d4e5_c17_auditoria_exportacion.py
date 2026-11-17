"""C-17 append-only audit and expiring tenant export jobs (Migration 011)."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e17a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "d14a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
TENANT_GUC = "current_setting('app.tenant_id')::uuid"


def _rls(table: str) -> None:
    op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text(
        f"CREATE POLICY {table}_isolation ON {table} FOR ALL TO PUBLIC "
        f"USING (tenant_id = {TENANT_GUC}) "
        f"WITH CHECK (tenant_id = {TENANT_GUC})"
    ))


def upgrade() -> None:
    op.create_table(
        "audit_evento",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_usuario_id", UUID, sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("evento", sa.String(64), nullable=False),
        sa.Column("recurso", sa.String(64), nullable=False),
        sa.Column("recurso_id", sa.String(80), nullable=True),
        sa.Column("metodo", sa.String(12), nullable=False),
        sa.Column("ruta", sa.String(255), nullable=False),
        sa.Column("detalles", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_evento_tenant_created", "audit_evento", ["tenant_id", "created_at"])
    op.create_index("ix_audit_evento_tenant_evento_created", "audit_evento", ["tenant_id", "evento", "created_at"])
    _rls("audit_evento")
    op.execute(sa.text("""
        CREATE FUNCTION audit_evento_no_mutacion() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_evento is append-only';
        END;
        $$ LANGUAGE plpgsql
    """))
    op.execute(sa.text("""
        CREATE TRIGGER audit_evento_no_update_delete
        BEFORE UPDATE OR DELETE ON audit_evento
        FOR EACH ROW EXECUTE FUNCTION audit_evento_no_mutacion()
    """))
    op.execute(sa.text("""
        CREATE TRIGGER audit_evento_no_truncate
        BEFORE TRUNCATE ON audit_evento
        FOR EACH STATEMENT EXECUTE FUNCTION audit_evento_no_mutacion()
    """))

    op.create_table(
        "exportacion",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("solicitada_por_usuario_id", UUID, sa.ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True),
        sa.Column("estado", sa.String(16), nullable=False, server_default=sa.text("'pendiente'")),
        sa.Column("storage_key", sa.String(255), nullable=True),
        sa.Column("error_code", sa.String(48), nullable=True),
        sa.Column("solicitada_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("generada_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vence_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("estado IN ('pendiente','procesando','lista','fallida','vencida')", name="exportacion_estado_enum"),
    )
    op.create_index("ix_exportacion_tenant_solicitada", "exportacion", ["tenant_id", "solicitada_at"])
    _rls("exportacion")


def downgrade() -> None:
    op.drop_index("ix_exportacion_tenant_solicitada", table_name="exportacion")
    op.execute(sa.text("DROP POLICY IF EXISTS exportacion_isolation ON exportacion"))
    op.drop_table("exportacion")
    op.execute(sa.text("DROP TRIGGER IF EXISTS audit_evento_no_update_delete ON audit_evento"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS audit_evento_no_truncate ON audit_evento"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS audit_evento_no_mutacion()"))
    op.drop_index("ix_audit_evento_tenant_evento_created", table_name="audit_evento")
    op.drop_index("ix_audit_evento_tenant_created", table_name="audit_evento")
    op.execute(sa.text("DROP POLICY IF EXISTS audit_evento_isolation ON audit_evento"))
    op.drop_table("audit_evento")
