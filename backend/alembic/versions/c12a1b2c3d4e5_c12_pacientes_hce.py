"""C-12 pacientes + HCE (Migración 008)."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c12a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "c11a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
GUC = "current_setting('app.tenant_id')::uuid"
TENANT_TABLES = (
    "paciente",
    "historia_clinica",
    "evolucion",
    "derivacion_hce",
)


def _rls_upgrade_sql() -> list[str]:
    """ENABLE + FORCE RLS + tenant isolation policy per C-12 table."""
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


def _append_only_upgrade_sql() -> list[str]:
    """DB-level append-only guard for evolucion (RN-HC-01, D5)."""
    return [
        """
        CREATE OR REPLACE FUNCTION evolucion_append_only()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'evolucion is append-only (RN-HC-01): '
                'create a new row referencing corrige_evolucion_id';
        END;
        $$ LANGUAGE plpgsql
        """,
        """
        CREATE TRIGGER evolucion_no_update
        BEFORE UPDATE ON evolucion
        FOR EACH ROW EXECUTE FUNCTION evolucion_append_only()
        """,
        """
        CREATE TRIGGER evolucion_no_delete
        BEFORE DELETE ON evolucion
        FOR EACH ROW EXECUTE FUNCTION evolucion_append_only()
        """,
    ]


def _append_only_downgrade_sql() -> list[str]:
    return [
        "DROP TRIGGER IF EXISTS evolucion_no_delete ON evolucion",
        "DROP TRIGGER IF EXISTS evolucion_no_update ON evolucion",
        "DROP FUNCTION IF EXISTS evolucion_append_only()",
    ]


def upgrade() -> None:
    op.create_table(
        "paciente",
        sa.Column(
            "id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("nombre", sa.String(160), nullable=False),
        sa.Column("dni", sa.String(20), nullable=True),
        sa.Column("telefono", sa.String(32), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("obra_social", sa.String(120), nullable=True),
        sa.Column(
            "consentimiento_datos",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("consentimiento_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_active",
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_paciente_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "NOT consentimiento_datos OR consentimiento_at IS NOT NULL",
            name="paciente_consentimiento_fecha_requerida",
        ),
        sa.CheckConstraint(
            "consentimiento_at IS NULL OR consentimiento_datos",
            name="paciente_consentimiento_sin_flag",
        ),
    )
    op.create_index("ix_paciente_tenant_id", "paciente", ["tenant_id"])
    op.create_index(
        "uq_paciente_tenant_dni_activo",
        "paciente",
        ["tenant_id", "dni"],
        unique=True,
        postgresql_where=sa.text("is_active AND dni IS NOT NULL"),
    )

    op.create_table(
        "historia_clinica",
        sa.Column(
            "id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("paciente_id", UUID, nullable=False),
        sa.Column("alergias", sa.Text(), nullable=True),
        sa.Column("medicacion", sa.Text(), nullable=True),
        sa.Column("antecedentes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_historia_clinica_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["paciente.id"],
            name="fk_historia_clinica_paciente_id_paciente",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "paciente_id",
            name="uq_historia_clinica_tenant_paciente",
        ),
    )
    op.create_index(
        "ix_historia_clinica_tenant_id", "historia_clinica", ["tenant_id"]
    )
    op.create_index(
        "ix_historia_clinica_paciente_id", "historia_clinica", ["paciente_id"]
    )

    op.create_table(
        "evolucion",
        sa.Column(
            "id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("historia_clinica_id", UUID, nullable=False),
        sa.Column("autor_usuario_id", UUID, nullable=False),
        sa.Column("autor_profesional_id", UUID, nullable=True),
        sa.Column("contenido", sa.Text(), nullable=False),
        sa.Column("corrige_evolucion_id", UUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_evolucion_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["historia_clinica_id"],
            ["historia_clinica.id"],
            name="fk_evolucion_historia_clinica_id_historia_clinica",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["autor_usuario_id"],
            ["usuario.id"],
            name="fk_evolucion_autor_usuario_id_usuario",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["autor_profesional_id"],
            ["profesional.id"],
            name="fk_evolucion_autor_profesional_id_profesional",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["corrige_evolucion_id"],
            ["evolucion.id"],
            name="fk_evolucion_corrige_evolucion_id_evolucion",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_evolucion_tenant_id", "evolucion", ["tenant_id"])
    op.create_index(
        "ix_evolucion_historia_clinica_id", "evolucion", ["historia_clinica_id"]
    )
    op.create_index(
        "ix_evolucion_autor_usuario_id", "evolucion", ["autor_usuario_id"]
    )
    op.create_index(
        "ix_evolucion_autor_profesional_id", "evolucion", ["autor_profesional_id"]
    )
    op.create_index(
        "ix_evolucion_corrige_evolucion_id", "evolucion", ["corrige_evolucion_id"]
    )

    op.create_table(
        "derivacion_hce",
        sa.Column(
            "id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("paciente_id", UUID, nullable=False),
        sa.Column("desde_profesional_id", UUID, nullable=True),
        sa.Column("hacia_profesional_id", UUID, nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("created_by_usuario_id", UUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_derivacion_hce_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["paciente.id"],
            name="fk_derivacion_hce_paciente_id_paciente",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["desde_profesional_id"],
            ["profesional.id"],
            name="fk_derivacion_hce_desde_profesional_id_profesional",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["hacia_profesional_id"],
            ["profesional.id"],
            name="fk_derivacion_hce_hacia_profesional_id_profesional",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_usuario_id"],
            ["usuario.id"],
            name="fk_derivacion_hce_created_by_usuario_id_usuario",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_derivacion_hce_tenant_id", "derivacion_hce", ["tenant_id"])
    op.create_index(
        "ix_derivacion_hce_paciente_id", "derivacion_hce", ["paciente_id"]
    )
    op.create_index(
        "ix_derivacion_hce_desde_profesional_id",
        "derivacion_hce",
        ["desde_profesional_id"],
    )
    op.create_index(
        "ix_derivacion_hce_hacia_profesional_id",
        "derivacion_hce",
        ["hacia_profesional_id"],
    )

    for statement in _rls_upgrade_sql():
        op.execute(sa.text(statement))
    for statement in _append_only_upgrade_sql():
        op.execute(sa.text(statement))


def downgrade() -> None:
    for statement in _append_only_downgrade_sql():
        op.execute(sa.text(statement))
    for statement in _rls_downgrade_sql():
        op.execute(sa.text(statement))
    op.drop_index(
        "ix_derivacion_hce_hacia_profesional_id", table_name="derivacion_hce"
    )
    op.drop_index(
        "ix_derivacion_hce_desde_profesional_id", table_name="derivacion_hce"
    )
    op.drop_index("ix_derivacion_hce_paciente_id", table_name="derivacion_hce")
    op.drop_index("ix_derivacion_hce_tenant_id", table_name="derivacion_hce")
    op.drop_table("derivacion_hce")
    op.drop_index("ix_evolucion_corrige_evolucion_id", table_name="evolucion")
    op.drop_index("ix_evolucion_autor_profesional_id", table_name="evolucion")
    op.drop_index("ix_evolucion_autor_usuario_id", table_name="evolucion")
    op.drop_index("ix_evolucion_historia_clinica_id", table_name="evolucion")
    op.drop_index("ix_evolucion_tenant_id", table_name="evolucion")
    op.drop_table("evolucion")
    op.drop_index(
        "ix_historia_clinica_paciente_id", table_name="historia_clinica"
    )
    op.drop_index("ix_historia_clinica_tenant_id", table_name="historia_clinica")
    op.drop_table("historia_clinica")
    op.drop_index("uq_paciente_tenant_dni_activo", table_name="paciente")
    op.drop_index("ix_paciente_tenant_id", table_name="paciente")
    op.drop_table("paciente")
