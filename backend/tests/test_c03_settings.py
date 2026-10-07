"""C-03 settings tests (task 2.2) — RED first.

Lifetimes (15 min access / 7 d refresh), PORTAL_SECRET fallback-with-warning,
ADMIN_INITIAL_PASSWORD + placeholder deny-list, prod CI check. Synthetic
values only; no live DB needed.
"""

from __future__ import annotations

import warnings

import pytest

BASE_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db",
    "JWT_SECRET": "fictitious-test-secret-not-real",
}


def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "DATABASE_URL",
        "JWT_SECRET",
        "JWT_ACCESS_MINUTES",
        "JWT_REFRESH_DAYS",
        "PORTAL_SECRET",
        "ADMIN_INITIAL_PASSWORD",
        "APP_ENV",
        "AUTH_RATE_LIMIT_PER_MINUTE",
        "AUTH_RATE_LIMIT_WINDOW_SECONDS",
        "WA_BSP_TOKEN",
        "WA_PHONE_ID",
        "MP_ACCESS_TOKEN",
        "SLOT_PUBLIC_BASE_URL",
        "REMINDER_T48H_HS",
        "REMINDER_T24H_HS",
        "DEFAULT_CANCEL_ANTICIP_HS",
    ):
        monkeypatch.delenv(var, raising=False)


def _settings(monkeypatch: pytest.MonkeyPatch, **extra: str):
    from app.shared.settings import Settings

    _clean_env(monkeypatch)
    for key, value in {**BASE_ENV, **extra}.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_auth_lifetime_defaults_are_15m_7d(monkeypatch: pytest.MonkeyPatch) -> None:
    """WHEN only secrets set THEN access=15min and refresh=7d per D8."""
    settings = _settings(monkeypatch)
    assert settings.jwt_access_minutes == 15
    assert settings.jwt_refresh_days == 7


def test_auth_lifetimes_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    """WHEN lifetimes set THEN settings honor them (independent literals)."""
    settings = _settings(monkeypatch, JWT_ACCESS_MINUTES="30", JWT_REFRESH_DAYS="14")
    assert settings.jwt_access_minutes == 30
    assert settings.jwt_refresh_days == 14


def test_portal_secret_falls_back_with_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN PORTAL_SECRET missing THEN falls back to JWT_SECRET + warns (D8)."""
    settings = _settings(monkeypatch)
    with pytest.warns(UserWarning, match="PORTAL_SECRET"):
        assert settings.portal_secret_value == "fictitious-test-secret-not-real"


def test_portal_secret_explicit_no_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    """WHEN PORTAL_SECRET set THEN used as-is with no fallback warning."""
    settings = _settings(monkeypatch, PORTAL_SECRET="fictitious-portal-secret")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert settings.portal_secret_value == "fictitious-portal-secret"


def test_prod_without_portal_secret_fails_ci_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN APP_ENV=prod without PORTAL_SECRET THEN CI check raises (D8/Risk)."""
    from app.shared.settings import require_portal_secret_for_prod

    settings = _settings(monkeypatch, APP_ENV="prod")
    with pytest.raises(ValueError, match="PORTAL_SECRET"):
        require_portal_secret_for_prod(settings)


def test_prod_with_portal_secret_passes_ci_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN APP_ENV=prod with PORTAL_SECRET THEN CI check passes silently."""
    from app.shared.settings import require_portal_secret_for_prod

    settings = _settings(
        monkeypatch, APP_ENV="prod", PORTAL_SECRET="fictitious-portal-secret"
    )
    require_portal_secret_for_prod(settings)  # must not raise


@pytest.mark.parametrize(
    "placeholder",
    ["changeme", "CHANGEME-123", "admin", "Admin", "password1", "test", "123456"],
)
def test_placeholder_passwords_denied(
    monkeypatch: pytest.MonkeyPatch, placeholder: str
) -> None:
    """WHEN ADMIN_INITIAL_PASSWORD is a placeholder THEN deny-list rejects."""
    from app.shared.settings import is_placeholder_password

    assert is_placeholder_password(placeholder) is True
    _clean_env(monkeypatch)
    assert is_placeholder_password("Str0ng!Fictitious-Seed-9") is False


def test_fail_fast_preserved_for_core_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN JWT_SECRET missing THEN startup still fails naming JWT_SECRET."""
    from pydantic import ValidationError

    from app.shared.settings import Settings

    _clean_env(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
    )
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)  # type: ignore[call-arg]
    assert "JWT_SECRET" in str(exc_info.value)


def test_rate_limit_defaults_5_per_60s(monkeypatch: pytest.MonkeyPatch) -> None:
    """WHEN unset THEN login rate limit defaults to 5 attempts per 60s (D5)."""
    settings = _settings(monkeypatch)
    assert settings.auth_rate_limit_per_minute == 5
    assert settings.auth_rate_limit_window_seconds == 60
