"""C-05 slot generator (RN-AG-04, D2): pure scheduling arithmetic.

``generate_slots`` is a total, deterministic function: no I/O, no global
clock, no schedule table. The caller (C-06 and the internal ``huecos``
endpoint) passes the working window explicitly; until a jornada model
exists (open question for C-06/C-07) the caller owns the window choice.

Grid: candidate starts at ``ventana_inicio`` stepping ``duracion + buffer``
minutes; each candidate blocks ``[inicio, inicio + paso)``. A candidate is
offered only when it overlaps NO existing turno and NO applicable bloqueo,
with half-open ``[inicio, fin)`` overlap semantics (a slot ending exactly
where an occupation starts does NOT overlap).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Slot:
    """Offered hole: ``[inicio, fin)`` with ``fin = inicio + duracion + buffer``."""

    inicio: datetime
    fin: datetime


@dataclass(frozen=True)
class Ocupacion:
    """Busy interval (turno or bloqueo) that discounts slots."""

    inicio: datetime
    fin: datetime


def _solapa(a_inicio: datetime, a_fin: datetime, b_inicio: datetime, b_fin: datetime) -> bool:
    """Half-open overlap: ``[a_inicio, a_fin)`` vs ``[b_inicio, b_fin)``."""
    return a_inicio < b_fin and b_inicio < a_fin


def generate_slots(
    *,
    ventana_inicio: datetime,
    ventana_fin: datetime,
    duracion_min: int,
    buffer_min: int,
    turnos: list[Ocupacion],
    bloqueos: list[Ocupacion],
) -> list[Slot]:
    """Generate candidate holes over the grid minus turnos and bloqueos.

    Raises ``ValueError`` fail-closed on an inverted window, non-positive
    duration or negative buffer — the caller must not offer holes then.
    """
    if ventana_fin <= ventana_inicio:
        raise ValueError("ventana_fin debe ser posterior a ventana_inicio")
    if duracion_min <= 0:
        raise ValueError("duracion_min debe ser positiva")
    if buffer_min < 0:
        raise ValueError("buffer_min no puede ser negativo")
    paso = timedelta(minutes=duracion_min + buffer_min)
    ocupados = list(turnos) + list(bloqueos)
    slots: list[Slot] = []
    inicio = ventana_inicio
    while inicio + paso <= ventana_fin:
        fin = inicio + paso
        if not any(
            _solapa(inicio, fin, oc.inicio, oc.fin) for oc in ocupados
        ):
            slots.append(Slot(inicio=inicio, fin=fin))
        inicio = inicio + paso
    return slots
