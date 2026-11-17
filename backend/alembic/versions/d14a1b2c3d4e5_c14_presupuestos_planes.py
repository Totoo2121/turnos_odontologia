"""C-14 presupuestos, planes y cuenta corriente (Migración 010)."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d14a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "c13a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
GUC = "current_setting('app.tenant_id')::uuid"
TENANT_TABLES = (
    "presupuesto",
    "presupuesto_item",
    "plan_tratamiento",
    "cuenta_corriente",
    "movimiento_cc",
)
ESTADOS_PRESUPUESTO = ("borrador", "enviado", "aceptado", "rechazado")
ESTADOS_PLAN = ("activo", "completado", "cancelado")
TIPOS_MOVIMIENTO = ("debito", "credito")
SUPERFICIES = (
    "oclusal",
    "mesial",
    "distal",
    "vestibular",
    "lingual",
    "palatina",
    "incisal",
)


def _in_clause(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


def _rls_upgrade_sql() -> list[str]:
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


def _trigger_upgrade_sql() -> list[str]:
    """Financial movements are append-only; budget lines freeze after send."""
    return [
        """
        CREATE OR REPLACE FUNCTION movimiento_cc_append_only()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'movimiento_cc is append-only: register a new movement instead '
                'of editing or deleting the record';
        END;
        $$ LANGUAGE plpgsql
        """,
        """
        CREATE TRIGGER movimiento_cc_no_update
        BEFORE UPDATE ON movimiento_cc
        FOR EACH ROW EXECUTE FUNCTION movimiento_cc_append_only()
        """,
        """
        CREATE TRIGGER movimiento_cc_no_delete
        BEFORE DELETE ON movimiento_cc
        FOR EACH ROW EXECUTE FUNCTION movimiento_cc_append_only()
        """,
        """
        CREATE OR REPLACE FUNCTION presupuesto_item_guard()
        RETURNS trigger AS $$
        DECLARE
            estado_padre text;
        BEGIN
            SELECT estado INTO estado_padre
            FROM presupuesto
            WHERE id = OLD.presupuesto_id;
            -- NULL means the parent was deleted: the CASCADE cleanup is allowed.
            IF estado_padre IS NOT NULL AND estado_padre <> 'borrador' THEN
                RAISE EXCEPTION
                    'presupuesto_item is read-only after the budget leaves '
                    'borrador';
            END IF;
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql
        """,
        """
        CREATE TRIGGER presupuesto_item_no_update
        BEFORE UPDATE ON presupuesto_item
        FOR EACH ROW EXECUTE FUNCTION presupuesto_item_guard()
        """,
        """
        CREATE TRIGGER presupuesto_item_no_delete
        BEFORE DELETE ON presupuesto_item
        FOR EACH ROW EXECUTE FUNCTION presupuesto_item_guard()
        """,
    ]


def _trigger_downgrade_sql() -> list[str]:
    return [
        "DROP TRIGGER IF EXISTS presupuesto_item_no_delete ON presupuesto_item",
        "DROP TRIGGER IF EXISTS presupuesto_item_no_update ON presupuesto_item",
        "DROP FUNCTION IF EXISTS presupuesto_item_guard()",
        "DROP TRIGGER IF EXISTS movimiento_cc_no_delete ON movimiento_cc",
        "DROP TRIGGER IF EXISTS movimiento_cc_no_update ON movimiento_cc",
        "DROP FUNCTION IF EXISTS movimiento_cc_append_only()",
    ]


def upgrade() -> None:
    op.add_column(
        "prestacion",
        sa.Column(
            "requiere_consentimiento",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.create_table(
        "presupuesto",
        sa.Column(
            "id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("paciente_id", UUID, nullable=False),
        sa.Column("historia_clinica_id", UUID, nullable=False),
        sa.Column("creado_por_usuario_id", UUID, nullable=False),
        sa.Column(
            "estado",
            sa.String(12),
            nullable=False,
            server_default=sa.text("'borrador'"),
        ),
        sa.Column(
            "moneda",
            sa.String(3),
            nullable=False,
            server_default=sa.text("'ARS'"),
        ),
        sa.Column(
            "total",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("validez_hasta", sa.Date(), nullable=False),
        sa.Column("enviado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("aceptado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rechazado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
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
            name="fk_presupuesto_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["paciente.id"],
            name="fk_presupuesto_paciente_id_paciente",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["historia_clinica_id"],
            ["historia_clinica.id"],
            name="fk_presupuesto_historia_clinica_id_historia_clinica",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["creado_por_usuario_id"],
            ["usuario.id"],
            name="fk_presupuesto_creado_por_usuario_id_usuario",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _in_clause("estado", ESTADOS_PRESUPUESTO),
            name="presupuesto_estado_enum",
        ),
        sa.CheckConstraint("moneda = 'ARS'", name="presupuesto_moneda_ars"),
        sa.CheckConstraint("total >= 0", name="presupuesto_total_nonneg"),
    )
    op.create_index("ix_presupuesto_tenant_id", "presupuesto", ["tenant_id"])
    op.create_index("ix_presupuesto_paciente_id", "presupuesto", ["paciente_id"])
    op.create_index(
        "ix_presupuesto_historia_clinica_id",
        "presupuesto",
        ["historia_clinica_id"],
    )
    op.create_index(
        "ix_presupuesto_tenant_paciente_estado",
        "presupuesto",
        ["tenant_id", "paciente_id", "estado"],
    )

    op.create_table(
        "presupuesto_item",
        sa.Column(
            "id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("presupuesto_id", UUID, nullable=False),
        sa.Column("prestacion_id", UUID, nullable=False),
        sa.Column("pieza_fdi", sa.SmallInteger(), nullable=True),
        sa.Column("superficie", sa.String(16), nullable=True),
        sa.Column("descripcion", sa.String(200), nullable=False),
        sa.Column(
            "cantidad",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("precio_unitario", sa.Numeric(12, 2), nullable=False),
        sa.Column("importe", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "etapa",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "requiere_consentimiento",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
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
            name="fk_presupuesto_item_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["presupuesto_id"],
            ["presupuesto.id"],
            name="fk_presupuesto_item_presupuesto_id_presupuesto",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["prestacion_id"],
            ["prestacion.id"],
            name="fk_presupuesto_item_prestacion_id_prestacion",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "cantidad > 0", name="presupuesto_item_cantidad_pos"
        ),
        sa.CheckConstraint(
            "precio_unitario >= 0", name="presupuesto_item_precio_nonneg"
        ),
        sa.CheckConstraint("importe >= 0", name="presupuesto_item_importe_nonneg"),
        sa.CheckConstraint(
            "etapa BETWEEN 1 AND 20", name="presupuesto_item_etapa_rango"
        ),
        sa.CheckConstraint(
            "pieza_fdi IS NULL OR (pieza_fdi BETWEEN 11 AND 48 "
            "AND (pieza_fdi % 10) BETWEEN 1 AND 8 "
            "AND (pieza_fdi / 10) BETWEEN 1 AND 4)",
            name="presupuesto_item_fdi_valida",
        ),
        sa.CheckConstraint(
            "superficie IS NULL OR " + _in_clause("superficie", SUPERFICIES),
            name="presupuesto_item_superficie_enum",
        ),
        sa.CheckConstraint(
            "superficie IS NULL OR pieza_fdi IS NOT NULL",
            name="presupuesto_item_superficie_exige_pieza",
        ),
    )
    op.create_index(
        "ix_presupuesto_item_tenant_id", "presupuesto_item", ["tenant_id"]
    )
    op.create_index(
        "ix_presupuesto_item_presupuesto_id",
        "presupuesto_item",
        ["presupuesto_id"],
    )
    op.create_index(
        "ix_presupuesto_item_prestacion_id",
        "presupuesto_item",
        ["prestacion_id"],
    )
    op.create_index(
        "ix_presupuesto_item_tenant_presupuesto_etapa",
        "presupuesto_item",
        ["tenant_id", "presupuesto_id", "etapa"],
    )

    op.create_table(
        "plan_tratamiento",
        sa.Column(
            "id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("presupuesto_id", UUID, nullable=False),
        sa.Column("paciente_id", UUID, nullable=False),
        sa.Column("consentimiento_id", UUID, nullable=True),
        sa.Column(
            "estado",
            sa.String(12),
            nullable=False,
            server_default=sa.text("'activo'"),
        ),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("etapas", sa.SmallInteger(), nullable=False),
        sa.Column(
            "etapa_actual",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("1"),
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
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_plan_tratamiento_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["presupuesto_id"],
            ["presupuesto.id"],
            name="fk_plan_tratamiento_presupuesto_id_presupuesto",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["paciente.id"],
            name="fk_plan_tratamiento_paciente_id_paciente",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["consentimiento_id"],
            ["consentimiento.id"],
            name="fk_plan_tratamiento_consentimiento_id_consentimiento",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "presupuesto_id",
            name="uq_plan_tenant_presupuesto",
        ),
        sa.CheckConstraint(
            _in_clause("estado", ESTADOS_PLAN),
            name="plan_tratamiento_estado_enum",
        ),
        sa.CheckConstraint("total >= 0", name="plan_tratamiento_total_nonneg"),
        sa.CheckConstraint("etapas >= 1", name="plan_tratamiento_etapas_pos"),
        sa.CheckConstraint(
            "etapa_actual BETWEEN 1 AND etapas",
            name="plan_tratamiento_etapa_actual_rango",
        ),
    )
    op.create_index(
        "ix_plan_tratamiento_tenant_id", "plan_tratamiento", ["tenant_id"]
    )
    op.create_index(
        "ix_plan_tratamiento_presupuesto_id",
        "plan_tratamiento",
        ["presupuesto_id"],
    )
    op.create_index(
        "ix_plan_tratamiento_paciente_id", "plan_tratamiento", ["paciente_id"]
    )
    op.create_index(
        "ix_plan_tratamiento_tenant_paciente",
        "plan_tratamiento",
        ["tenant_id", "paciente_id"],
    )

    op.create_table(
        "cuenta_corriente",
        sa.Column(
            "id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("paciente_id", UUID, nullable=False),
        sa.Column(
            "moneda",
            sa.String(3),
            nullable=False,
            server_default=sa.text("'ARS'"),
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
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_cuenta_corriente_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["paciente.id"],
            name="fk_cuenta_corriente_paciente_id_paciente",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id", "paciente_id", name="uq_cc_tenant_paciente"
        ),
        sa.CheckConstraint("moneda = 'ARS'", name="cuenta_corriente_moneda_ars"),
    )
    op.create_index(
        "ix_cuenta_corriente_tenant_id", "cuenta_corriente", ["tenant_id"]
    )
    op.create_index(
        "ix_cuenta_corriente_paciente_id", "cuenta_corriente", ["paciente_id"]
    )

    op.create_table(
        "movimiento_cc",
        sa.Column(
            "id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("cuenta_id", UUID, nullable=False),
        sa.Column("plan_tratamiento_id", UUID, nullable=True),
        sa.Column("tipo", sa.String(8), nullable=False),
        sa.Column("monto", sa.Numeric(12, 2), nullable=False),
        sa.Column("descripcion", sa.String(200), nullable=False),
        sa.Column("referencia", sa.String(80), nullable=True),
        sa.Column(
            "ocurrido_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
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
            name="fk_movimiento_cc_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cuenta_id"],
            ["cuenta_corriente.id"],
            name="fk_movimiento_cc_cuenta_id_cuenta_corriente",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_tratamiento_id"],
            ["plan_tratamiento.id"],
            name="fk_movimiento_cc_plan_tratamiento_id_plan_tratamiento",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "referencia",
            name="uq_movimiento_cc_tenant_referencia",
        ),
        sa.CheckConstraint(
            _in_clause("tipo", TIPOS_MOVIMIENTO),
            name="movimiento_cc_tipo_enum",
        ),
        sa.CheckConstraint("monto > 0", name="movimiento_cc_monto_pos"),
    )
    op.create_index(
        "ix_movimiento_cc_tenant_id", "movimiento_cc", ["tenant_id"]
    )
    op.create_index(
        "ix_movimiento_cc_cuenta_id", "movimiento_cc", ["cuenta_id"]
    )
    op.create_index(
        "ix_movimiento_cc_plan_tratamiento_id",
        "movimiento_cc",
        ["plan_tratamiento_id"],
    )
    op.create_index(
        "ix_movimiento_cc_tenant_cuenta_ocurrido",
        "movimiento_cc",
        ["tenant_id", "cuenta_id", "ocurrido_at"],
    )

    for statement in _rls_upgrade_sql():
        op.execute(sa.text(statement))
    for statement in _trigger_upgrade_sql():
        op.execute(sa.text(statement))


def downgrade() -> None:
    for statement in _trigger_downgrade_sql():
        op.execute(sa.text(statement))
    for statement in _rls_downgrade_sql():
        op.execute(sa.text(statement))
    op.drop_index(
        "ix_movimiento_cc_tenant_cuenta_ocurrido", table_name="movimiento_cc"
    )
    op.drop_index(
        "ix_movimiento_cc_plan_tratamiento_id", table_name="movimiento_cc"
    )
    op.drop_index("ix_movimiento_cc_cuenta_id", table_name="movimiento_cc")
    op.drop_index("ix_movimiento_cc_tenant_id", table_name="movimiento_cc")
    op.drop_table("movimiento_cc")
    op.drop_index(
        "ix_cuenta_corriente_paciente_id", table_name="cuenta_corriente"
    )
    op.drop_index(
        "ix_cuenta_corriente_tenant_id", table_name="cuenta_corriente"
    )
    op.drop_table("cuenta_corriente")
    op.drop_index(
        "ix_plan_tratamiento_tenant_paciente", table_name="plan_tratamiento"
    )
    op.drop_index(
        "ix_plan_tratamiento_paciente_id", table_name="plan_tratamiento"
    )
    op.drop_index(
        "ix_plan_tratamiento_presupuesto_id", table_name="plan_tratamiento"
    )
    op.drop_index(
        "ix_plan_tratamiento_tenant_id", table_name="plan_tratamiento"
    )
    op.drop_table("plan_tratamiento")
    op.drop_index(
        "ix_presupuesto_item_tenant_presupuesto_etapa",
        table_name="presupuesto_item",
    )
    op.drop_index(
        "ix_presupuesto_item_prestacion_id", table_name="presupuesto_item"
    )
    op.drop_index(
        "ix_presupuesto_item_presupuesto_id", table_name="presupuesto_item"
    )
    op.drop_index(
        "ix_presupuesto_item_tenant_id", table_name="presupuesto_item"
    )
    op.drop_table("presupuesto_item")
    op.drop_index(
        "ix_presupuesto_tenant_paciente_estado", table_name="presupuesto"
    )
    op.drop_index(
        "ix_presupuesto_historia_clinica_id", table_name="presupuesto"
    )
    op.drop_index("ix_presupuesto_paciente_id", table_name="presupuesto")
    op.drop_index("ix_presupuesto_tenant_id", table_name="presupuesto")
    op.drop_table("presupuesto")
    op.drop_column("prestacion", "requiere_consentimiento")
