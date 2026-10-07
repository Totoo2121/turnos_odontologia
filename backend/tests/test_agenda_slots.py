"""C-05 slot generator tests (task 3.1) — RED first.

Pure function: no DB, no clock, deterministic. Window passed explicitly by
the caller (D2 — no schedule table in this change).
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

from datetime import UTC, datetime, timedelta

import pytest

from app.application.agenda_slots import Ocupacion, Slot, generate_slots


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 12, 25, hour, minute, tzinfo=UTC)


def test_grilla_45_mas_10_desplaza_paso_55() -> None:
    """WHEN Limpieza 45'+10 desde 09:00 libre THEN 09:00/09:55/10:50 sin solape."""
    slots = generate_slots(
        ventana_inicio=_dt(9),
        ventana_fin=_dt(12),
        duracion_min=45,
        buffer_min=10,
        turnos=[],
        bloqueos=[],
    )
    inicios = [(s.inicio.hour, s.inicio.minute) for s in slots]
    assert inicios == [(9, 0), (9, 55), (10, 50)]
    for first, second in zip(slots, slots[1:]):
        assert first.fin <= second.inicio


def test_huecos_descuentan_turno_y_bloqueo() -> None:
    """WHEN turno 10:00-10:30 + bloqueo 12:00-13:00 THEN se omiten y el resto va."""
    slots = generate_slots(
        ventana_inicio=_dt(9),
        ventana_fin=_dt(13),
        duracion_min=30,
        buffer_min=0,
        turnos=[Ocupacion(inicio=_dt(10), fin=_dt(10, 30))],
        bloqueos=[Ocupacion(inicio=_dt(12), fin=_dt(13))],
    )
    inicios = [(s.inicio.hour, s.inicio.minute) for s in slots]
    assert (10, 0) not in inicios
    assert (12, 0) not in inicios
    assert (12, 30) not in inicios
    assert inicios == [(9, 0), (9, 30), (10, 30), (11, 0), (11, 30)]


def test_borde_fin_inicio_no_solapa() -> None:
    """WHEN turno termina donde empieza el slot THEN el slot se ofrece ([,))."""
    slots = generate_slots(
        ventana_inicio=_dt(9),
        ventana_fin=_dt(11),
        duracion_min=30,
        buffer_min=0,
        turnos=[Ocupacion(inicio=_dt(9, 30), fin=_dt(10))],
        bloqueos=[],
    )
    inicios = [(s.inicio.hour, s.inicio.minute) for s in slots]
    assert (9, 0) in inicios  # [09:00,09:30) vs [09:30,10:00): borde, no solapa
    assert (10, 0) in inicios  # [10:00,10:30) vs [09:30,10:00): borde, no solapa
    assert (9, 30) not in inicios


def test_solape_parcial_de_turno_bloquea_slot() -> None:
    """WHEN turno 10:10-10:40 THEN bloquea 10:00 y 10:30 (triangula parcial)."""
    slots = generate_slots(
        ventana_inicio=_dt(9),
        ventana_fin=_dt(12),
        duracion_min=30,
        buffer_min=0,
        turnos=[Ocupacion(inicio=_dt(10, 10), fin=_dt(10, 40))],
        bloqueos=[],
    )
    inicios = [(s.inicio.hour, s.inicio.minute) for s in slots]
    assert (10, 0) not in inicios
    assert (10, 30) not in inicios
    assert (9, 30) in inicios
    assert (11, 0) in inicios


def test_ventana_invalida_rechazada() -> None:
    """WHEN ventana_fin<=ventana_inicio THEN ValueError (fail-closed)."""
    with pytest.raises(ValueError):
        generate_slots(
            ventana_inicio=_dt(12),
            ventana_fin=_dt(12),
            duracion_min=30,
            buffer_min=0,
            turnos=[],
            bloqueos=[],
        )
    with pytest.raises(ValueError):
        generate_slots(
            ventana_inicio=_dt(13),
            ventana_fin=_dt(12),
            duracion_min=30,
            buffer_min=0,
            turnos=[],
            bloqueos=[],
        )


def test_duracion_no_positiva_rechazada() -> None:
    """WHEN duracion<=0 o buffer<0 THEN ValueError."""
    with pytest.raises(ValueError):
        generate_slots(
            ventana_inicio=_dt(9),
            ventana_fin=_dt(12),
            duracion_min=0,
            buffer_min=0,
            turnos=[],
            bloqueos=[],
        )
    with pytest.raises(ValueError):
        generate_slots(
            ventana_inicio=_dt(9),
            ventana_fin=_dt(12),
            duracion_min=30,
            buffer_min=-5,
            turnos=[],
            bloqueos=[],
        )


def test_slot_fin_incluye_buffer_y_respeta_ventana() -> None:
    """WHEN slot excede ventana THEN se excluye (fin<=ventana_fin siempre)."""
    slots = generate_slots(
        ventana_inicio=_dt(9),
        ventana_fin=_dt(9, 30),
        duracion_min=45,
        buffer_min=10,
        turnos=[],
        bloqueos=[],
    )
    assert slots == []  # 09:00+55=09:55 excede la ventana: ningun slot cabe
    slots2 = generate_slots(
        ventana_inicio=_dt(9),
        ventana_fin=_dt(9, 55),
        duracion_min=45,
        buffer_min=10,
        turnos=[],
        bloqueos=[],
    )
    assert len(slots2) == 1
    assert slots2[0].fin == _dt(9, 55)
    assert isinstance(slots2[0], Slot)
    assert all(s.fin <= _dt(9, 55) for s in slots2)


def test_sin_ocupacion_grilla_completa() -> None:
    """WHEN jornada libre 09:00-11:00 paso 30 THEN 4 huecos exactos."""
    slots = generate_slots(
        ventana_inicio=_dt(9),
        ventana_fin=_dt(11),
        duracion_min=30,
        buffer_min=0,
        turnos=[],
        bloqueos=[],
    )
    assert [(s.inicio.hour, s.inicio.minute) for s in slots] == [
        (9, 0),
        (9, 30),
        (10, 0),
        (10, 30),
    ]
    assert all(isinstance(s, Slot) for s in slots)
    assert all((s.fin - s.inicio) == timedelta(minutes=30) for s in slots)
