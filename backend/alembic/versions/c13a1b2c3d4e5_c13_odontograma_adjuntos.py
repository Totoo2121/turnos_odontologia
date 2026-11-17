"""C-13 odontograma, adjuntos y consentimientos (Migración 009)."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c13a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "c12a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
GUC = "current_setting('app.tenant_id')::uuid"
TENANT_TABLES = ("odontograma", "evento_pieza", "adjunto", "consentimiento")

ESTADOS_PIEZA = (
    "sano",
    "caries",
    "obturacion",
    "corona",
    "endodoncia",
    "extraccion",
    "implante",
    "sellador",
)
SUPERFICIES = (
    "oclusal",
    "mesial",
    "distal",
    "vestibular",
    "lingual",
    "palatina",
    "incisal",
)
TIPOS_ADJUNTO = ("rx", "foto", "documento")
TIPOS_CONSENTIMIENTO = (
    "tratamiento",
    "invasivo",
    "cirugia",
    "ortodoncia",
    "datos",
)


def _in_clause(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


def _rls_upgrade_sql() -> list[str]:
    """ENABLE + FORCE RLS + tenant isolation policy per C-13 table."""
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
    """DB-level append-only guard for evento_pieza (RN-HC-02, D4)."""
    return [
        """
        CREATE OR REPLACE FUNCTION evento_pieza_append_only()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'evento_pieza is append-only (RN-HC-02): '
                'register a new event instead of editing the record';
        END;
        $$ LANGUAGE plpgsql
        """,
        """
        CREATE TRIGGER evento_pieza_no_update
        BEFORE UPDATE ON evento_pieza
        FOR EACH ROW EXECUTE FUNCTION evento_pieza_append_only()
        """,
        """
        CREATE TRIGGER evento_pieza_no_delete
        BEFORE DELETE ON evento_pieza
        FOR EACH ROW EXECUTE FUNCTION evento_pieza_append_only()
        """,
    ]


def _append_only_downgrade_sql() -> list[str]:
    return [
        "DROP TRIGGER IF EXISTS evento_pieza_no_delete ON evento_pieza",
        "DROP TRIGGER IF EXISTS evento_pieza_no_update ON evento_pieza",
        "DROP FUNCTION IF EXISTS evento_pieza_append_only()",
    ]


def upgrade() -> None:
    op.create_table(
        "odontograma",
        sa.Column(
            "id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("historia_clinica_id", UUID, nullable=False),
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
            name="fk_odontograma_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["historia_clinica_id"],
            ["historia_clinica.id"],
            name="fk_odontograma_historia_clinica_id_historia_clinica",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "historia_clinica_id",
            name="uq_odontograma_tenant_historia",
        ),
    )
    op.create_index("ix_odontograma_tenant_id", "odontograma", ["tenant_id"])
    op.create_index(
        "ix_odontograma_historia_clinica_id",
        "odontograma",
        ["historia_clinica_id"],
    )

    op.create_table(
        "evento_pieza",
        sa.Column(
            "id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("odontograma_id", UUID, nullable=False),
        sa.Column("pieza_fdi", sa.SmallInteger(), nullable=False),
        sa.Column("superficie", sa.String(16), nullable=True),
        sa.Column("estado", sa.String(16), nullable=False),
        sa.Column(
            "fecha",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("autor_usuario_id", UUID, nullable=False),
        sa.Column("autor_profesional_id", UUID, nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_evento_pieza_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["odontograma_id"],
            ["odontograma.id"],
            name="fk_evento_pieza_odontograma_id_odontograma",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["autor_usuario_id"],
            ["usuario.id"],
            name="fk_evento_pieza_autor_usuario_id_usuario",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["autor_profesional_id"],
            ["profesional.id"],
            name="fk_evento_pieza_autor_profesional_id_profesional",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "pieza_fdi BETWEEN 11 AND 48 "
            "AND (pieza_fdi % 10) BETWEEN 1 AND 8 "
            "AND (pieza_fdi / 10) BETWEEN 1 AND 4",
            name="evento_pieza_fdi_valida",
        ),
        sa.CheckConstraint(
            "superficie IS NULL OR " + _in_clause("superficie", SUPERFICIES),
            name="evento_pieza_superficie_enum",
        ),
        sa.CheckConstraint(
            _in_clause("estado", ESTADOS_PIEZA),
            name="evento_pieza_estado_enum",
        ),
        sa.CheckConstraint(
            "estado NOT IN ('caries', 'obturacion', 'sellador') "
            "OR superficie IS NOT NULL",
            name="evento_pieza_superficie_requerida",
        ),
        sa.CheckConstraint(
            "estado NOT IN ('corona', 'endodoncia', 'extraccion', 'implante') "
            "OR superficie IS NULL",
            name="evento_pieza_superficie_prohibida",
        ),
    )
    op.create_index("ix_evento_pieza_tenant_id", "evento_pieza", ["tenant_id"])
    op.create_index(
        "ix_evento_pieza_odontograma_id", "evento_pieza", ["odontograma_id"]
    )
    op.create_index(
        "ix_evento_pieza_autor_usuario_id",
        "evento_pieza",
        ["autor_usuario_id"],
    )
    op.create_index(
        "ix_evento_pieza_autor_profesional_id",
        "evento_pieza",
        ["autor_profesional_id"],
    )
    op.create_index(
        "ix_evento_pieza_estado_actual",
        "evento_pieza",
        ["tenant_id", "odontograma_id", "pieza_fdi", "superficie", "fecha"],
    )

    op.create_table(
        "adjunto",
        sa.Column(
            "id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("historia_clinica_id", UUID, nullable=False),
        sa.Column("tipo", sa.String(16), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False),
        sa.Column("nombre_original", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("origen", sa.String(40), nullable=True),
        sa.Column("subido_por_usuario_id", UUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_adjunto_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["historia_clinica_id"],
            ["historia_clinica.id"],
            name="fk_adjunto_historia_clinica_id_historia_clinica",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subido_por_usuario_id"],
            ["usuario.id"],
            name="fk_adjunto_subido_por_usuario_id_usuario",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "storage_key",
            name="uq_adjunto_tenant_storage_key",
        ),
        sa.CheckConstraint(
            _in_clause("tipo", TIPOS_ADJUNTO), name="adjunto_tipo_enum"
        ),
        sa.CheckConstraint("size_bytes > 0", name="adjunto_size_positivo"),
        sa.CheckConstraint(
            "char_length(sha256) = 64", name="adjunto_sha256_hex"
        ),
    )
    op.create_index("ix_adjunto_tenant_id", "adjunto", ["tenant_id"])
    op.create_index(
        "ix_adjunto_historia_clinica_id", "adjunto", ["historia_clinica_id"]
    )

    op.create_table(
        "consentimiento",
        sa.Column(
            "id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("paciente_id", UUID, nullable=False),
        sa.Column("historia_clinica_id", UUID, nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("texto_version", sa.String(40), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column(
            "plan_invasivo",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("firmante_nombre", sa.String(160), nullable=False),
        sa.Column("firmante_dni", sa.String(20), nullable=True),
        sa.Column("firmado_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip", sa.String(64), nullable=False),
        sa.Column("dispositivo", sa.String(255), nullable=False),
        sa.Column("firma_hash", sa.String(64), nullable=False),
        sa.Column("pdf_storage_key", sa.String(255), nullable=False),
        sa.Column("pdf_sha256", sa.String(64), nullable=False),
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
            name="fk_consentimiento_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["paciente.id"],
            name="fk_consentimiento_paciente_id_paciente",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["historia_clinica_id"],
            ["historia_clinica.id"],
            name="fk_consentimiento_historia_clinica_id_historia_clinica",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_usuario_id"],
            ["usuario.id"],
            name="fk_consentimiento_created_by_usuario_id_usuario",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            _in_clause("tipo", TIPOS_CONSENTIMIENTO),
            name="consentimiento_tipo_enum",
        ),
        sa.CheckConstraint(
            "char_length(firma_hash) = 64",
            name="consentimiento_firma_hash_hex",
        ),
        sa.CheckConstraint(
            "char_length(pdf_sha256) = 64",
            name="consentimiento_pdf_sha256_hex",
        ),
    )
    op.create_index(
        "ix_consentimiento_tenant_id", "consentimiento", ["tenant_id"]
    )
    op.create_index(
        "ix_consentimiento_paciente_id", "consentimiento", ["paciente_id"]
    )
    op.create_index(
        "ix_consentimiento_historia_clinica_id",
        "consentimiento",
        ["historia_clinica_id"],
    )
    op.create_index(
        "ix_consentimiento_paciente_invasivo",
        "consentimiento",
        ["tenant_id", "paciente_id", "plan_invasivo"],
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
        "ix_consentimiento_paciente_invasivo", table_name="consentimiento"
    )
    op.drop_index(
        "ix_consentimiento_historia_clinica_id", table_name="consentimiento"
    )
    op.drop_index("ix_consentimiento_paciente_id", table_name="consentimiento")
    op.drop_index("ix_consentimiento_tenant_id", table_name="consentimiento")
    op.drop_table("consentimiento")
    op.drop_index("ix_adjunto_historia_clinica_id", table_name="adjunto")
    op.drop_index("ix_adjunto_tenant_id", table_name="adjunto")
    op.drop_table("adjunto")
    op.drop_index("ix_evento_pieza_estado_actual", table_name="evento_pieza")
    op.drop_index(
        "ix_evento_pieza_autor_profesional_id", table_name="evento_pieza"
    )
    op.drop_index(
        "ix_evento_pieza_autor_usuario_id", table_name="evento_pieza"
    )
    op.drop_index("ix_evento_pieza_odontograma_id", table_name="evento_pieza")
    op.drop_index("ix_evento_pieza_tenant_id", table_name="evento_pieza")
    op.drop_table("evento_pieza")
    op.drop_index(
        "ix_odontograma_historia_clinica_id", table_name="odontograma"
    )
    op.drop_index("ix_odontograma_tenant_id", table_name="odontograma")
    op.drop_table("odontograma")
