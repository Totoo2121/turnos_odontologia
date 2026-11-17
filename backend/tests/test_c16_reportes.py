"""C-16 report invariants without relying on live clinic data."""

from __future__ import annotations

import datetime as dt
import os
import asyncio
import uuid

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db")
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest

from app.application.agenda_cobros import AGENDA_TZ
from app.application.reportes import bounds, report_scope, tasa_ausentismo
from app.shared.exceptions import AppError


def test_report_period_is_inclusive_and_uses_clinic_timezone() -> None:
    desde = dt.date(2026, 11, 1)
    hasta = dt.date(2026, 11, 3)
    inicio, fin = bounds(desde, hasta)
    assert inicio == dt.datetime(2026, 11, 1, tzinfo=AGENDA_TZ)
    assert fin == dt.datetime(2026, 11, 4, tzinfo=AGENDA_TZ)


@pytest.mark.parametrize(
    ("desde", "hasta"),
    [(dt.date(2026, 11, 2), dt.date(2026, 11, 1)),
     (dt.date(2025, 1, 1), dt.date(2026, 1, 3))],
)
def test_report_period_rejects_inverted_or_unbounded_range(
    desde: dt.date, hasta: dt.date
) -> None:
    with pytest.raises(AppError) as error:
        bounds(desde, hasta)
    assert error.value.status_code == 422


def test_absence_rate_uses_literal_counts_and_handles_empty_period() -> None:
    assert tasa_ausentismo(2, 5) == 40.0
    assert tasa_ausentismo(0, 0) == 0.0


def test_owner_sees_tenant_scope_without_professional_lookup() -> None:
    class NoQuery:
        async def scalar(self, _query):
            raise AssertionError("owner scope must not need a professional lookup")

    alcance, profesional_id = asyncio.run(report_scope(
        NoQuery(),  # type: ignore[arg-type]
        uuid.uuid4(),
        ("propietario",),
        "10000000-0000-0000-0000-000000000001",
    ))
    assert (alcance, profesional_id) == ("total", None)
