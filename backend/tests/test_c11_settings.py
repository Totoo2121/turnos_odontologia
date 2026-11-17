"""C-11 task 2.1: settings for WhatsApp webhook, SMTP and notification policy."""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

from pathlib import Path

import pytest

from app.shared.settings import Settings


def test_notification_defaults_are_safe() -> None:
    """WHEN only secrets set THEN notification settings use safe defaults."""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.whatsapp_webhook_secret == ""
    assert settings.smtp_host == "localhost"
    assert settings.smtp_port == 587
    assert settings.smtp_password == ""
    assert settings.smtp_from == "no-reply@turnos.invalid"
    assert settings.confirmation_threshold_hs == 24
    assert settings.recall_ausente_dias == 7
    assert settings.notif_max_intentos == 3
    assert settings.notif_backoff_base_s == 0.5


def test_notification_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """WHEN C-11 vars set THEN Settings reads them."""
    monkeypatch.setenv("WHATSAPP_WEBHOOK_SECRET", "fictitious-webhook-secret")
    monkeypatch.setenv("SMTP_HOST", "smtp.demo-ficticio.invalid")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_USER", "demo-ficticio")
    monkeypatch.setenv("SMTP_PASSWORD", "fictitious-smtp-secret")
    monkeypatch.setenv("SMTP_FROM", "turnos@demo-ficticio.invalid")
    monkeypatch.setenv("CONFIRMATION_THRESHOLD_HS", "12")
    monkeypatch.setenv("RECALL_AUSENTE_DIAS", "10")
    monkeypatch.setenv("NOTIF_MAX_INTENTOS", "5")
    monkeypatch.setenv("NOTIF_BACKOFF_BASE_S", "1.5")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.whatsapp_webhook_secret == "fictitious-webhook-secret"
    assert settings.smtp_host == "smtp.demo-ficticio.invalid"
    assert settings.smtp_port == 2525
    assert settings.smtp_user == "demo-ficticio"
    assert settings.smtp_password == "fictitious-smtp-secret"
    assert settings.smtp_from == "turnos@demo-ficticio.invalid"
    assert settings.confirmation_threshold_hs == 12
    assert settings.recall_ausente_dias == 10
    assert settings.notif_max_intentos == 5
    assert settings.notif_backoff_base_s == 1.5


def test_env_example_documents_c11_vars() -> None:
    """WHEN .env.example inspected THEN every C-11 variable is documented."""
    root = Path(__file__).resolve().parents[2]
    content = (root / ".env.example").read_text(encoding="utf-8")
    for name in (
        "WHATSAPP_WEBHOOK_SECRET",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USER",
        "SMTP_PASSWORD",
        "SMTP_FROM",
        "CONFIRMATION_THRESHOLD_HS",
        "RECALL_AUSENTE_DIAS",
        "NOTIF_MAX_INTENTOS",
        "NOTIF_BACKOFF_BASE_S",
    ):
        assert f"{name}=" in content
