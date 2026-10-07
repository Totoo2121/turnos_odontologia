"""C-05 catalogo-agenda models tests (task 1.1) — RED first.

Metadata/transient seams run without a DB. Behavioral persistence scenarios
are Postgres-gated and SKIP honestly when no live DB is reachable.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import uuid
from typing import Any

import pytest
from sqlalchemy import CheckConstraint, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.domain.agenda.models import (
    Bloqueo,
    Prestacion,
    Profesional,
    ProfesionalPrestacion,
    Sillon,
)
from app.domain.models import Base


def _table(model: Any) -> Table:
    """Table metadata by model (typed seam; avoids __table__ plugin gaps)."""
    return Base.metadata.tables[model.__tablename__]


# --- 1. Tables registered on the shared metadata, lowercase names ---


def test_all_five_agenda_tables_registered_lowercase() -> None:
    """WHEN shared metadata inspected THEN the 5 C-05 tables exist lowercase."""
    for name in (
        "profesional",
        "sillon",
        "prestacion",
        "profesional_prestacion",
        "bloqueo",
    ):
        assert name in Base.metadata.tables, f"missing table: {name}"
        assert name == name.lower()


def test_agenda_tablenames_match_models() -> None:
    """WHEN models inspected THEN __tablename__ matches the registered table."""
    for model in (Profesional, Sillon, Prestacion, ProfesionalPrestacion, Bloqueo):
        assert model.__tablename__ in Base.metadata.tables


def test_all_pks_are_native_uuid() -> None:
    """WHEN tables inspected THEN every PK is a native UUID column."""
    for model in (Profesional, Sillon, Prestacion, ProfesionalPrestacion, Bloqueo):
        pk_cols = list(_table(model).primary_key.columns)
        assert len(pk_cols) == 1
        assert isinstance(pk_cols[0].type, PG_UUID), model.__tablename__


# --- 2. Tenant scoping: tenant_id FK + index on all 5 ---


def test_all_five_tables_carry_indexed_tenant_id() -> None:
    """WHEN tables inspected THEN tenant_id FK present and indexed."""
    for model in (Profesional, Sillon, Prestacion, ProfesionalPrestacion, Bloqueo):
        table = _table(model)
        assert "tenant_id" in table.columns, model.__tablename__
        assert table.c.tenant_id.nullable is False
        assert table.c.tenant_id.foreign_keys, f"{model.__tablename__}.tenant_id no FK"
        covered = any(
            "tenant_id" in {c.name for c in index.columns}
            for index in table.indexes
        )
        assert covered, f"{model.__tablename__}.tenant_id lacks index"


def test_prestacion_unique_tenant_nombre() -> None:
    """WHEN prestacion inspected THEN UNIQUE(tenant_id, nombre) exists."""
    table = _table(Prestacion)
    found = any(
        isinstance(const, UniqueConstraint)
        and {c.name for c in const.columns} == {"tenant_id", "nombre"}
        for const in table.constraints
    )
    assert found, "missing UNIQUE(tenant_id, nombre) on prestacion"


def test_sillon_unique_tenant_nombre_and_nullable_sucursal() -> None:
    """WHEN sillon inspected THEN UNIQUE(tenant_id, nombre); sucursal NULL."""
    table = _table(Sillon)
    assert table.c.sucursal_id.nullable is True
    found = any(
        isinstance(const, UniqueConstraint)
        and {c.name for c in const.columns} == {"tenant_id", "nombre"}
        for const in table.constraints
    )
    assert found, "missing UNIQUE(tenant_id, nombre) on sillon"


def test_profesional_link_unique_pair() -> None:
    """WHEN link table inspected THEN UNIQUE(profesional_id, prestacion_id)."""
    table = _table(ProfesionalPrestacion)
    found = any(
        isinstance(const, UniqueConstraint)
        and {c.name for c in const.columns} == {"profesional_id", "prestacion_id"}
        for const in table.constraints
    )
    assert found, "missing UNIQUE(profesional_id, prestacion_id)"


# --- 3. CHECK constraints: duracion_min > 0, fin > inicio, motivo enum ---


def test_prestacion_duracion_positiva_constraint() -> None:
    """WHEN prestacion inspected THEN CHECK(duracion_min > 0) exists."""
    table = _table(Prestacion)
    checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    assert checks, "expected CHECK constraints on prestacion"
    assert any(
        "duracion_min" in str(c.sqltext) and ">" in str(c.sqltext) for c in checks
    ), "missing CHECK(duracion_min > 0)"


def test_prestacion_buffer_no_negativo_constraint() -> None:
    """WHEN prestacion inspected THEN CHECK(buffer_min >= 0) exists."""
    table = _table(Prestacion)
    checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    assert any("buffer_min" in str(c.sqltext) for c in checks)


def test_bloqueo_fin_despues_inicio_constraint() -> None:
    """WHEN bloqueo inspected THEN CHECK(fin > inicio) exists."""
    table = _table(Bloqueo)
    checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    assert checks, "expected CHECK constraints on bloqueo"
    assert any(
        "fin" in str(c.sqltext) and "inicio" in str(c.sqltext) for c in checks
    ), "missing CHECK(fin > inicio)"


def test_bloqueo_motivo_enum_constraint() -> None:
    """WHEN bloqueo inspected THEN motivo restricted to the 4 valid values."""
    table = _table(Bloqueo)
    checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    assert any("motivo" in str(c.sqltext) for c in checks)
    assert set(Bloqueo.MOTIVOS_VALIDOS) == {
        "feriado",
        "licencia",
        "administrativo",
        "mantenimiento",
    }


def test_bloqueo_exige_al_menos_un_objetivo_constraint() -> None:
    """WHEN bloqueo inspected THEN CHECK(profesional OR sillon) exists."""
    table = _table(Bloqueo)
    assert table.c.profesional_id.nullable is True
    assert table.c.sillon_id.nullable is True
    checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    assert any(
        "profesional_id" in str(c.sqltext) and "sillon_id" in str(c.sqltext)
        for c in checks
    ), "missing CHECK(al menos un objetivo)"


# --- 4. AuditMixin lifecycle + link table without soft-delete ---


def test_audit_columns_on_four_entities() -> None:
    """WHEN catalog entities inspected THEN audit columns exist."""
    for model in (Profesional, Sillon, Prestacion, Bloqueo):
        table = _table(model)
        for column in ("is_active", "created_at", "updated_at", "deleted_at"):
            assert column in table.columns, f"{model.__tablename__}.{column}"


def test_link_table_has_only_created_at() -> None:
    """WHEN link table inspected THEN only created_at, no soft-delete columns."""
    table = _table(ProfesionalPrestacion)
    assert "created_at" in table.columns
    assert "deleted_at" not in table.columns
    assert "is_active" not in table.columns


def test_profesional_nullable_usuario_and_matricula() -> None:
    """WHEN profesional inspected THEN usuario_id/matricula NULL; nombre NOT NULL."""
    table = _table(Profesional)
    assert table.c.usuario_id.nullable is True
    assert table.c.matricula.nullable is True
    assert table.c.nombre.nullable is False


def test_fk_columns_are_indexed() -> None:
    """WHEN tables inspected THEN every FK column has an index."""
    for model in (Profesional, Sillon, ProfesionalPrestacion, Bloqueo):
        table = _table(model)
        for column in table.columns:
            if column.foreign_keys:
                covered = any(
                    column.name in {c.name for c in index.columns}
                    for index in table.indexes
                )
                assert covered, f"{model.__tablename__}.{column.name} lacks index"


def test_profesional_duracion_default_positiva_constraint() -> None:
    """WHEN profesional inspected THEN CHECK(duracion_default_min > 0) exists."""
    table = _table(Profesional)
    checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    assert any("duracion_default_min" in str(c.sqltext) for c in checks)
