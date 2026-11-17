"""Exact ARS money helpers for C-14 (no binary floats at the boundary)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.shared.exceptions import AppError

CENT = Decimal("0.01")


def to_decimal(value: Any) -> Decimal:
    """Parse a value into Decimal, rejecting anything that is not a number."""
    if isinstance(value, bool):
        raise AppError("monto invalido", 422)
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise AppError("monto invalido", 422) from None
    if not parsed.is_finite():
        raise AppError("monto invalido", 422)
    return parsed


def money(value: Any) -> Decimal:
    """Quantize an ARS amount to cents with half-up rounding."""
    return to_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)
