"""Settings tests (C-01 task 1.2) — synthetic values only."""

import pytest
from pydantic import ValidationError


def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "DATABASE_URL",
        "JWT_SECRET",
        "WA_BSP_TOKEN",
        "WA_PHONE_ID",
        "MP_ACCESS_TOKEN",
        "SLOT_PUBLIC_BASE_URL",
        "REMINDER_T48H_HS",
        "REMINDER_T24H_HS",
        "DEFAULT_CANCEL_ANTICIP_HS",
    ):
        monkeypatch.delenv(var, raising=False)


def test_missing_jwt_secret_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """WHEN JWT_SECRET missing THEN startup fails naming JWT_SECRET."""
    _clean_env(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
    )
    from app.shared.settings import Settings

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)  # type: ignore[call-arg]
    assert "JWT_SECRET" in str(exc_info.value)


def test_missing_database_url_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """WHEN DATABASE_URL missing THEN startup fails naming DATABASE_URL."""
    _clean_env(monkeypatch)
    monkeypatch.setenv("JWT_SECRET", "fictitious-test-secret-not-real")
    from app.shared.settings import Settings

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)  # type: ignore[call-arg]
    assert "DATABASE_URL" in str(exc_info.value)


def test_full_synthetic_env_loads_with_expected_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN all 9 vars set THEN settings load with those values."""
    _clean_env(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
    )
    monkeypatch.setenv("JWT_SECRET", "fictitious-test-secret-not-real")
    monkeypatch.setenv("WA_BSP_TOKEN", "fictitious-wa-token")
    monkeypatch.setenv("WA_PHONE_ID", "fictitious-phone-id")
    monkeypatch.setenv("MP_ACCESS_TOKEN", "fictitious-mp-token")
    monkeypatch.setenv("SLOT_PUBLIC_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("REMINDER_T48H_HS", "48")
    monkeypatch.setenv("REMINDER_T24H_HS", "24")
    monkeypatch.setenv("DEFAULT_CANCEL_ANTICIP_HS", "12")
    from app.shared.settings import Settings

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.jwt_secret == "fictitious-test-secret-not-real"
    assert settings.database_url == (
        "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
    )
    assert settings.reminder_t48h_hs == 48
    assert settings.reminder_t24h_hs == 24
    assert settings.default_cancel_anticip_hs == 12


def test_non_sensitive_defaults_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    """WHEN only secrets set THEN non-sensitive vars use safe defaults."""
    _clean_env(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
    )
    monkeypatch.setenv("JWT_SECRET", "fictitious-test-secret-not-real")
    from app.shared.settings import Settings

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.reminder_t48h_hs == 48
    assert settings.reminder_t24h_hs == 24
    assert settings.default_cancel_anticip_hs == 24
    # Integration stubs default to empty (not configured), never to a real token.
    assert settings.wa_bsp_token == ""
    assert settings.mp_access_token == ""
    assert "real" not in settings.wa_bsp_token
