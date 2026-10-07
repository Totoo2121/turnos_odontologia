"""C-05 immutability contract tests (task 4.3) — RED first.

RN-AG-03: editing ``prestacion.duracion_min``/buffer must NOT rewrite
existing turnos — each turno freezes its effective duration at creation
(C-06 implements the real snapshot; here a stub pins the contract).
No DB needed.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.application.agenda_immutability import FrozenTurno, freeze_turno


def _migration_source() -> str:
    return (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "c05a1b2c3d4e5_c05_agenda_catalog.py"
    ).read_text(encoding="utf-8")


def test_migracion_sin_trigger_ni_backfill_de_duracion() -> None:
    """WHEN migracion 003 inspeccionada THEN ningun trigger/backfill toca turnos."""
    source = _migration_source()
    assert "TRIGGER" not in source.upper()
    assert "UPDATE prestacion SET" not in source


def test_turno_congelado_conserva_fin_tras_editar_prestacion() -> None:
    """WHEN duracion 30→45 THEN el turno existente conserva su fin original."""
    inicio = datetime(2026, 12, 25, 10, 0, tzinfo=UTC)
    turno = freeze_turno(
        turno_id=uuid.uuid4(),
        prestacion_id=uuid.uuid4(),
        inicio=inicio,
        duracion_min=30,
        buffer_min=0,
    )
    assert turno.fin == datetime(2026, 12, 25, 10, 30, tzinfo=UTC)
    # La prestacion cambia a 45+10: el turno congelado NO se reescribe.
    assert turno.duracion_min_snapshot == 30
    nuevo = freeze_turno(
        turno_id=uuid.uuid4(),
        prestacion_id=turno.prestacion_id,
        inicio=datetime(2026, 12, 26, 10, 0, tzinfo=UTC),
        duracion_min=45,
        buffer_min=10,
    )
    assert nuevo.fin == datetime(2026, 12, 26, 10, 55, tzinfo=UTC)
    assert turno.fin == datetime(2026, 12, 25, 10, 30, tzinfo=UTC)


def test_snapshot_es_inmutable_por_construccion() -> None:
    """WHEN snapshot congelado THEN sus campos no mutan (frozen, 2do input)."""
    import dataclasses

    turno = freeze_turno(
        turno_id=uuid.uuid4(),
        prestacion_id=uuid.uuid4(),
        inicio=datetime(2026, 12, 25, 10, 0, tzinfo=UTC),
        duracion_min=30,
        buffer_min=5,
    )
    assert isinstance(turno, FrozenTurno)
    try:
        turno.duracion_min_snapshot = 99  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("FrozenTurno debe ser inmutable")
    assert turno.fin == datetime(2026, 12, 25, 10, 35, tzinfo=UTC)
