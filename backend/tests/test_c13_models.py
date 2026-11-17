"""C-13 task 1.1: odontogram/adjunto/consentimiento model shape (RED first)."""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

from sqlalchemy import CheckConstraint, UniqueConstraint

from app.domain.clinica.models import (
    Adjunto,
    Consentimiento,
    EventoPieza,
    Odontograma,
)
from app.shared.db import metadata


def _checks(table) -> dict[str, str]:  # type: ignore[no-untyped-def]
    """Map declared check name (prefix stripped) to its SQL text.

    The shared metadata convention renders ``ck_<table>_<name>``; stripping the
    prefix keeps the assertions tied to the declared domain name.
    """
    prefix = f"ck_{table.name}_"
    return {
        (
            constraint.name[len(prefix) :]
            if constraint.name.startswith(prefix)
            else constraint.name
        ): str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name
    }


def test_c13_tables_registered_on_shared_metadata() -> None:
    """WHEN metadata inspected THEN the 4 C-13 tables are visible."""
    for name in (
        "odontograma",
        "evento_pieza",
        "adjunto",
        "consentimiento",
    ):
        assert name in metadata.tables, f"missing table: {name}"


def test_odontograma_is_one_per_history() -> None:
    """WHEN Odontograma inspected THEN UNIQUE(tenant_id, historia_clinica_id)."""
    table = Odontograma.__table__
    assert {"tenant_id", "historia_clinica_id", "created_at"} <= set(
        table.columns.keys()
    )
    unique = {
        constraint.name: constraint
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }["uq_odontograma_tenant_historia"]
    assert {column.name for column in unique.columns} == {
        "tenant_id",
        "historia_clinica_id",
    }


def test_evento_pieza_columns_and_append_only_shape() -> None:
    """WHEN EventoPieza inspected THEN FDI fields and no updated_at."""
    table = EventoPieza.__table__
    assert {
        "tenant_id",
        "odontograma_id",
        "pieza_fdi",
        "superficie",
        "estado",
        "fecha",
        "autor_usuario_id",
        "autor_profesional_id",
        "created_at",
    } <= set(table.columns.keys())
    assert "updated_at" not in table.columns
    assert table.c.pieza_fdi.nullable is False
    assert table.c.superficie.nullable is True
    assert table.c.autor_usuario_id.nullable is False
    assert table.c.autor_profesional_id.nullable is True


def test_evento_pieza_fdi_and_surface_checks() -> None:
    """WHEN EventoPieza inspected THEN FDI/surface/state checks exist."""
    checks = _checks(EventoPieza.__table__)
    assert "evento_pieza_fdi_valida" in checks
    assert "BETWEEN 11 AND 48" in checks["evento_pieza_fdi_valida"]
    assert "evento_pieza_superficie_enum" in checks
    assert "evento_pieza_estado_enum" in checks
    assert "evento_pieza_superficie_requerida" in checks
    assert "evento_pieza_superficie_prohibida" in checks


def test_evento_pieza_has_current_state_index() -> None:
    """WHEN EventoPieza inspected THEN the state projection index exists."""
    index = {idx.name for idx in EventoPieza.__table__.indexes}
    assert "ix_evento_pieza_estado_actual" in index


def test_adjunto_never_references_a_turno() -> None:
    """WHEN Adjunto inspected THEN it binds to history and has no turno_id."""
    table = Adjunto.__table__
    assert "turno_id" not in table.columns
    assert table.c.historia_clinica_id.nullable is False
    assert {
        "tipo",
        "storage_key",
        "nombre_original",
        "content_type",
        "size_bytes",
        "sha256",
        "origen",
        "subido_por_usuario_id",
    } <= set(table.columns.keys())
    unique = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert "uq_adjunto_tenant_storage_key" in unique


def test_adjunto_checks() -> None:
    """WHEN Adjunto inspected THEN type/size/hash are guarded in DB."""
    checks = _checks(Adjunto.__table__)
    assert "adjunto_tipo_enum" in checks
    assert "adjunto_size_positivo" in checks
    assert "adjunto_sha256_hex" in checks


def test_consentimiento_columns_and_checks() -> None:
    """WHEN Consentimiento inspected THEN signature/PDF fields are guarded."""
    table = Consentimiento.__table__
    assert {
        "paciente_id",
        "historia_clinica_id",
        "tipo",
        "texto",
        "texto_version",
        "plan_invasivo",
        "firmante_nombre",
        "firmante_dni",
        "firmado_at",
        "ip",
        "dispositivo",
        "firma_hash",
        "pdf_storage_key",
        "pdf_sha256",
        "created_by_usuario_id",
    } <= set(table.columns.keys())
    checks = _checks(table)
    assert "consentimiento_tipo_enum" in checks
    assert "consentimiento_firma_hash_hex" in checks
    assert "consentimiento_pdf_sha256_hex" in checks
    index = {idx.name for idx in table.indexes}
    assert "ix_consentimiento_paciente_invasivo" in index
