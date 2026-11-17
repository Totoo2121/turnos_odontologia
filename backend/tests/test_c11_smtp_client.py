"""C-11 task 2.3: SMTP email adapter wraps blocking errors asynchronously."""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest

from app.infrastructure.smtp import (
    FakeEmailClient,
    SmtpEmailClient,
    TransientEmailError,
)


def test_fake_email_client_records_and_replays_failures() -> None:
    """WHEN fake failure queued THEN it raises once and then records the send."""
    fake = FakeEmailClient()
    fake.failures.append(TransientEmailError("fictitious smtp down"))
    with pytest.raises(TransientEmailError):
        asyncio.run(fake.send(to="demo@ficticio.invalid", subject="s", body="b"))
    asyncio.run(fake.send(to="demo@ficticio.invalid", subject="s", body="b"))
    assert fake.sent == [
        {"to": "demo@ficticio.invalid", "subject": "s", "body": "b"}
    ]


def test_smtp_connection_error_is_reported_without_breaking_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN smtplib fails THEN the async API raises a retryable email error."""

    def explode(self, to: str, subject: str, body: str) -> None:  # type: ignore[no-untyped-def]
        raise OSError("fictitious connection refused")

    monkeypatch.setattr(SmtpEmailClient, "_send_sync", explode)
    client = SmtpEmailClient(host="smtp.ficticio.invalid")
    with pytest.raises(TransientEmailError):
        asyncio.run(client.send(to="demo@ficticio.invalid", subject="s", body="b"))


def test_smtp_send_success_runs_in_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN smtplib succeeds THEN send resolves without blocking the loop."""
    calls: list[tuple[str, str, str]] = []

    def record(self, to: str, subject: str, body: str) -> None:  # type: ignore[no-untyped-def]
        calls.append((to, subject, body))

    monkeypatch.setattr(SmtpEmailClient, "_send_sync", record)
    client = SmtpEmailClient(host="smtp.ficticio.invalid")
    asyncio.run(client.send(to="demo@ficticio.invalid", subject="s", body="b"))
    assert calls == [("demo@ficticio.invalid", "s", "b")]
