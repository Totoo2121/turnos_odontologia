"""C-05 immutability contract stub (RN-AG-03, D8).

Turnos do not exist yet in C-05, so there is nothing to backfill — and
migration 003 deliberately contains no trigger on ``prestacion``. The real
snapshot lands in C-06: every turno MUST copy (freeze) ``duracion_min``,
``buffer_min``, price and rules at creation, so later catalog edits only
affect future turnos.

This stub pins that contract: ``freeze_turno`` computes ``fin`` ONCE from
the prestacion parameters in force at creation; the frozen instance is
immutable afterwards. C-06 replaces the stub with the real ``turno``
snapshot (same ``fin = inicio + duracion + buffer`` arithmetic).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class FrozenTurno:
    """Turno snapshot stub: effective duration frozen at creation (C-06 real)."""

    turno_id: uuid.UUID
    prestacion_id: uuid.UUID
    inicio: datetime
    fin: datetime
    duracion_min_snapshot: int
    buffer_min_snapshot: int


def freeze_turno(
    *,
    turno_id: uuid.UUID,
    prestacion_id: uuid.UUID,
    inicio: datetime,
    duracion_min: int,
    buffer_min: int,
) -> FrozenTurno:
    """Freeze a turno's effective window (``fin = inicio + duracion + buffer``).

    Raises ``ValueError`` fail-closed on non-positive durations so a broken
    catalog can never mint a zero-length snapshot.
    """
    if duracion_min <= 0:
        raise ValueError("duracion_min debe ser positiva para congelar el turno")
    if buffer_min < 0:
        raise ValueError("buffer_min no puede ser negativo para congelar el turno")
    fin = inicio + timedelta(minutes=duracion_min + buffer_min)
    return FrozenTurno(
        turno_id=turno_id,
        prestacion_id=prestacion_id,
        inicio=inicio,
        fin=fin,
        duracion_min_snapshot=duracion_min,
        buffer_min_snapshot=buffer_min,
    )
