"""C-14 task 1.5: PRESUPUESTO_VALIDEZ_DIAS default and validation."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest
from pydantic import ValidationError

from app.shared.settings import Settings


def test_default_validity_is_30_days() -> None:
    """WHEN no env override THEN a quote lives 30 days by default."""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.presupuesto_validez_dias == 30


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRESUPUESTO_VALIDEZ_DIAS", "15")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.presupuesto_validez_dias == 15


@pytest.mark.parametrize("value", ["0", "-5"])
def test_non_positive_validity_fails(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("PRESUPUESTO_VALIDEZ_DIAS", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_env_example_documents_c14_var() -> None:
    root = Path(__file__).resolve().parents[2]
    content = (root / ".env.example").read_text(encoding="utf-8")
    assert "PRESUPUESTO_VALIDEZ_DIAS=" in content
