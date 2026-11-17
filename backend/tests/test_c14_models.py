"""C-14 tasks 1.1/1.2: catalog flag + budget models on the shared metadata."""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

from sqlalchemy import CheckConstraint, UniqueConstraint

from app.domain.agenda.models import Prestacion
from app.domain.clinica.models import (
    CuentaCorriente,
    MovimientoCC,
    PlanTratamiento,
    Presupuesto,
    PresupuestoItem,
)
from app.shared.db import metadata


def _checks(table) -> dict[str, str]:  # type: ignore[no-untyped-def]
    prefix = f"ck_{table.name}_"
    return {
        (
            constraint.name[len(prefix) :]
            if constraint.name.startswith(prefix)
            else constraint.name
        ): str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }


def _uniques(table) -> set[str]:  # type: ignore[no-untyped-def]
    return {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def test_prestacion_inherits_consent_flag() -> None:
    """WHEN Prestacion inspected THEN the invasive flag defaults to false."""
    column = Prestacion.__table__.c.requiere_consentimiento
    assert column.nullable is False
    assert column.default is not None and column.default.arg is False
    assert column.server_default is not None
    assert "false" in str(column.server_default.arg).lower()


def test_five_new_tables_are_registered() -> None:
    """WHEN app metadata inspected THEN C-14 tables are visible to Alembic."""
    expected = {
        "presupuesto",
        "presupuesto_item",
        "plan_tratamiento",
        "cuenta_corriente",
        "movimiento_cc",
    }
    assert expected <= set(metadata.tables)


def test_presupuesto_columns_and_checks() -> None:
    """WHEN Presupuesto inspected THEN money/state columns and checks exist."""
    table = Presupuesto.__table__
    assert {
        "id",
        "tenant_id",
        "paciente_id",
        "historia_clinica_id",
        "creado_por_usuario_id",
        "estado",
        "moneda",
        "total",
        "validez_hasta",
        "enviado_at",
        "aceptado_at",
        "rechazado_at",
        "observaciones",
        "created_at",
        "updated_at",
    } <= set(table.columns.keys())
    checks = _checks(table)
    assert "presupuesto_estado_enum" in checks
    assert "'borrador'" in checks["presupuesto_estado_enum"]
    assert "presupuesto_moneda_ars" in checks
    assert "presupuesto_total_nonneg" in checks
    indexes = {index.name for index in table.indexes}
    assert "ix_presupuesto_tenant_paciente_estado" in indexes


def test_presupuesto_item_columns_and_checks() -> None:
    """WHEN PresupuestoItem inspected THEN FDI/surface/stage guards exist."""
    table = PresupuestoItem.__table__
    assert {
        "presupuesto_id",
        "prestacion_id",
        "pieza_fdi",
        "superficie",
        "descripcion",
        "cantidad",
        "precio_unitario",
        "importe",
        "etapa",
        "requiere_consentimiento",
    } <= set(table.columns.keys())
    checks = _checks(table)
    assert "presupuesto_item_cantidad_pos" in checks
    assert "presupuesto_item_precio_nonneg" in checks
    assert "presupuesto_item_importe_nonneg" in checks
    assert "presupuesto_item_etapa_rango" in checks
    assert "presupuesto_item_fdi_valida" in checks
    assert "presupuesto_item_superficie_enum" in checks
    assert "presupuesto_item_superficie_exige_pieza" in checks
    indexes = {index.name for index in table.indexes}
    assert "ix_presupuesto_item_tenant_presupuesto_etapa" in indexes


def test_plan_tratamiento_unique_and_checks() -> None:
    """WHEN PlanTratamiento inspected THEN one plan per budget is enforced."""
    table = PlanTratamiento.__table__
    assert "uq_plan_tenant_presupuesto" in _uniques(table)
    checks = _checks(table)
    assert "plan_tratamiento_estado_enum" in checks
    assert "plan_tratamiento_total_nonneg" in checks
    assert "plan_tratamiento_etapas_pos" in checks
    assert "plan_tratamiento_etapa_actual_rango" in checks


def test_cuenta_corriente_unique_per_patient() -> None:
    """WHEN CuentaCorriente inspected THEN one account per tenant/patient."""
    table = CuentaCorriente.__table__
    assert "uq_cc_tenant_paciente" in _uniques(table)
    assert "saldo" not in table.columns
    assert "cuenta_corriente_moneda_ars" in _checks(table)


def test_movimiento_cc_reference_and_type_checks() -> None:
    """WHEN MovimientoCC inspected THEN append-only ledger invariants exist."""
    table = MovimientoCC.__table__
    assert "uq_movimiento_cc_tenant_referencia" in _uniques(table)
    checks = _checks(table)
    assert "movimiento_cc_tipo_enum" in checks
    assert "'debito'" in checks["movimiento_cc_tipo_enum"]
    assert "'credito'" in checks["movimiento_cc_tipo_enum"]
    assert "movimiento_cc_monto_pos" in checks
    indexes = {index.name for index in table.indexes}
    assert "ix_movimiento_cc_tenant_cuenta_ocurrido" in indexes
