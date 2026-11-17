"""C-11 SMTP email adapter (fallback channel).

``smtplib`` is blocking, so the real client sends inside ``run_in_executor``
to keep the FastAPI/Celery event loop responsive. Tests use ``FakeEmailClient``.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from typing import Any, Protocol


class EmailError(Exception):
    """Base email delivery error."""


class TransientEmailError(EmailError):
    """Retryable delivery failure."""


class PermanentEmailError(EmailError):
    """Non-retryable delivery failure (bad address/configuration)."""


class EmailClient(Protocol):
    """Port: send a plain-text email."""

    async def send(self, *, to: str, subject: str, body: str) -> None: ...


class SmtpEmailClient:
    """Minimal SMTP client (STARTTLS when configured)."""

    def __init__(
        self,
        *,
        host: str = "localhost",
        port: int = 587,
        user: str = "",
        password: str = "",
        from_addr: str = "no-reply@turnos.invalid",
        timeout: float = 10.0,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._from = from_addr
        self._timeout = timeout

    async def send(self, *, to: str, subject: str, body: str) -> None:
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self._send_sync, to, subject, body)
        except (OSError, smtplib.SMTPException) as exc:
            raise TransientEmailError(str(exc)) from exc

    def _send_sync(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
            smtp.ehlo()
            if self._port != 25:
                try:
                    smtp.starttls()
                    smtp.ehlo()
                except smtplib.SMTPException:
                    # Server without STARTTLS: keep the message unencrypted in
                    # local/dev; production requires a TLS-capable relay.
                    pass
            if self._user:
                smtp.login(self._user, self._password)
            smtp.send_message(message)


class FakeEmailClient:
    """Test double: records sends and replays queued failures."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.failures: list[Exception] = []

    async def send(self, *, to: str, subject: str, body: str) -> None:
        if self.failures:
            raise self.failures.pop(0)
        self.sent.append({"to": to, "subject": subject, "body": body})


def build_email_client(settings: Any) -> SmtpEmailClient:
    """Build the production SMTP client from typed settings."""
    return SmtpEmailClient(
        host=settings.smtp_host,
        port=settings.smtp_port,
        user=settings.smtp_user,
        password=settings.smtp_password,
        from_addr=settings.smtp_from,
    )
