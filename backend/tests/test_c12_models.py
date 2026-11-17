"""C-12 task 1.1: pacientes + HCE model shape (RED first)."""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

from sqlalchemy import CheckConstraint, UniqueConstraint

from app.domain.pacientes.models import (
    DerivacionHCE,
    Evolucion,
    HistoriaClinica,
    Paciente,
)
from app.shared.db import metadata


def _checks(table) -> set[str]:  # type: ignore[no-untyped-def]
    return {
        c.name
        for c in table.constraints
        if isinstance(c, CheckConstraint) and c.name
    }


def test_c12_tables_registered_on_shared_metadata() -> None:
    """WHEN metadata inspected THEN the 4 C-12 tables are visible."""
    for name in (
        "paciente",
        "historia_clinica",
        "evolucion",
        "derivacion_hce",
    ):
        assert name in metadata.tables, f"missing table: {name}"


def test_paciente_columns_and_audit_mixin() -> None:
    """WHEN Paciente inspected THEN identity + consent + lifecycle columns."""
    table = Paciente.__table__
    assert {
        "tenant_id",
        "nombre",
        "telefono",
        "dni",
        "email",
        "obra_social",
        "consentimiento_datos",
        "consentimiento_at",
        "is_active",
        "created_at",
        "updated_at",
        "deleted_at",
    } <= set(table.columns.keys())
    assert table.c.dni.nullable is True
    assert table.c.consentimiento_datos.nullable is False


def test_paciente_partial_unique_dni_index() -> None:
    """WHEN Paciente inspected THEN DNI uniqueness is partial by active row."""
    indexes = {idx.name: idx for idx in Paciente.__table__.indexes}
    index = indexes["uq_paciente_tenant_dni_activo"]
    assert index.unique is True
    assert {col.name for col in index.columns} == {"tenant_id", "dni"}


def test_paciente_consent_checks() -> None:
    """WHEN Paciente inspected THEN consent has coherent CHECK constraints."""
    names = _checks(Paciente.__table__)
    assert any(name.endswith("consentimiento_fecha_requerida") for name in names)
    assert any(name.endswith("consentimiento_sin_flag") for name in names)


def test_historia_unique_per_tenant_and_paciente() -> None:
    """WHEN HistoriaClinica inspected THEN UNIQUE(tenant_id, paciente_id)."""
    constraints = {
        c.name: c
        for c in HistoriaClinica.__table__.constraints
        if isinstance(c, UniqueConstraint)
    }
    unique = constraints["uq_historia_clinica_tenant_paciente"]
    assert {col.name for col in unique.columns} == {"tenant_id", "paciente_id"}
    assert "alergias" in HistoriaClinica.__table__.columns
    assert "medicacion" in HistoriaClinica.__table__.columns
    assert "antecedentes" in HistoriaClinica.__table__.columns


def test_evolucion_is_append_only_shape() -> None:
    """WHEN Evolucion inspected THEN author, correction FK and no updated_at."""
    table = Evolucion.__table__
    assert {
        "historia_clinica_id",
        "autor_usuario_id",
        "autor_profesional_id",
        "contenido",
        "corrige_evolucion_id",
        "created_at",
    } <= set(table.columns.keys())
    assert "updated_at" not in table.columns
    assert table.c.autor_usuario_id.nullable is False
    self_fk = {
        fk.target_fullname for fk in table.c.corrige_evolucion_id.foreign_keys
    }
    assert self_fk == {"evolucion.id"}


def test_derivacion_columns() -> None:
    """WHEN DerivacionHCE inspected THEN from/to professionals + patient."""
    table = DerivacionHCE.__table__
    assert {
        "tenant_id",
        "paciente_id",
        "desde_profesional_id",
        "hacia_profesional_id",
        "motivo",
        "created_by_usuario_id",
        "created_at",
    } <= set(table.columns.keys())
    assert table.c.hacia_profesional_id.nullable is False
