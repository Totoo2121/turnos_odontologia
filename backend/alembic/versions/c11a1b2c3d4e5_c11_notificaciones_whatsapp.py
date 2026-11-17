"""C-11 notificaciones whatsapp (Migración 007)."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c11a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "c10a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
GUC = "current_setting('app.tenant_id')::uuid"
TENANT_TABLES = ("plantilla_mensaje", "recordatorio")


def _rls_upgrade_sql() -> list[str]:
    """ENABLE + FORCE RLS + tenant isolation policy per C-11 table."""
    statements: list[str] = []
    for table in TENANT_TABLES:
        statements.append(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        statements.append(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        statements.append(
            f"CREATE POLICY {table}_isolation ON {table} FOR ALL TO PUBLIC "
            f"USING (tenant_id = {GUC}) WITH CHECK (tenant_id = {GUC})"
        )
    return statements


def _rls_downgrade_sql() -> list[str]:
    return [
        f"DROP POLICY IF EXISTS {table}_isolation ON {table}"
        for table in TENANT_TABLES
    ]


def upgrade() -> None:
    op.add_column(
        "turno", sa.Column("contacto_whatsapp", sa.String(32), nullable=True)
    )
    op.add_column(
        "turno", sa.Column("contacto_email", sa.String(320), nullable=True)
    )
    op.add_column(
        "turno",
        sa.Column("confirmado_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "prestacion",
        sa.Column("intervalo_control_dias", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "intervalo_control_dias_pos",
        "prestacion",
        "intervalo_control_dias IS NULL OR intervalo_control_dias > 0",
    )

    op.create_table(
        "plantilla_mensaje",
        sa.Column(
            "id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("clave", sa.String(64), nullable=False),
        sa.Column("canal", sa.String(16), nullable=False),
        sa.Column(
            "idioma",
            sa.String(8),
            nullable=False,
            server_default=sa.text("'es'"),
        ),
        sa.Column(
            "version", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column("cuerpo", sa.Text(), nullable=False),
        sa.Column("meta_template_name", sa.String(128), nullable=True),
        sa.Column(
            "activo",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_plantilla_mensaje_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "clave",
            "canal",
            "idioma",
            "version",
            name="uq_plantilla_mensaje_version",
        ),
        sa.CheckConstraint(
            "canal IN ('whatsapp', 'email')", name="plantilla_canal_enum"
        ),
        sa.CheckConstraint("version > 0", name="plantilla_version_pos"),
    )
    op.create_index(
        "ix_plantilla_mensaje_tenant_id", "plantilla_mensaje", ["tenant_id"]
    )

    op.create_table(
        "recordatorio",
        sa.Column(
            "id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("turno_id", UUID, nullable=False),
        sa.Column("paciente_id", UUID, nullable=True),
        sa.Column("canal", sa.String(16), nullable=False),
        sa.Column("tipo", sa.String(32), nullable=False),
        sa.Column("plantilla", sa.String(64), nullable=False),
        sa.Column("destinatario", sa.String(320), nullable=True),
        sa.Column("enviar_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "estado",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'pendiente'"),
        ),
        sa.Column(
            "intentos",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("ultimo_error", sa.Text(), nullable=True),
        sa.Column("confirmado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_recordatorio_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["turno_id"],
            ["turno.id"],
            name="fk_recordatorio_turno_id_turno",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "turno_id", "canal", "tipo", name="uq_recordatorio_turno_canal_tipo"
        ),
        sa.CheckConstraint(
            "canal IN ('whatsapp', 'email', 'interno')",
            name="recordatorio_canal_enum",
        ),
        sa.CheckConstraint(
            "tipo IN ('t48h', 't24h', 'confirmacion', 'recall_ausente', "
            "'control', 'aviso_recepcion')",
            name="recordatorio_tipo_enum",
        ),
        sa.CheckConstraint(
            "estado IN ('pendiente', 'enviado', 'fallido', 'confirmado', "
            "'cancelado')",
            name="recordatorio_estado_enum",
        ),
        sa.CheckConstraint("intentos >= 0", name="recordatorio_intentos_nonneg"),
    )
    op.create_index("ix_recordatorio_tenant_id", "recordatorio", ["tenant_id"])
    op.create_index("ix_recordatorio_turno_id", "recordatorio", ["turno_id"])
    op.create_index("ix_recordatorio_paciente_id", "recordatorio", ["paciente_id"])

    for statement in _rls_upgrade_sql():
        op.execute(sa.text(statement))


def downgrade() -> None:
    for statement in _rls_downgrade_sql():
        op.execute(sa.text(statement))
    op.drop_index("ix_recordatorio_paciente_id", table_name="recordatorio")
    op.drop_index("ix_recordatorio_turno_id", table_name="recordatorio")
    op.drop_index("ix_recordatorio_tenant_id", table_name="recordatorio")
    op.drop_table("recordatorio")
    op.drop_index(
        "ix_plantilla_mensaje_tenant_id", table_name="plantilla_mensaje"
    )
    op.drop_table("plantilla_mensaje")
    op.drop_constraint(
        "intervalo_control_dias_pos", "prestacion", type_="check"
    )
    op.drop_column("prestacion", "intervalo_control_dias")
    op.drop_column("turno", "confirmado_at")
    op.drop_column("turno", "contacto_email")
    op.drop_column("turno", "contacto_whatsapp")
