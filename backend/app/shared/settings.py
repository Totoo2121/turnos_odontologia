"""Typed environment settings (Pydantic v2 fail-fast).

All values come from the environment only. Required secrets (DATABASE_URL,
JWT_SECRET) have NO defaults so the process fails at startup naming the
missing variable. Integration tokens default to "" (not configured stub).
"""

import warnings

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Deny-list of placeholder passwords (D1/D8): the seed and CI refuse these
# case-insensitively so a copied `.env.example` value can never become a real
# credential. `*_PREFIX` entries deny any value starting with the token
# (design notation `changeme*`, `password*`); `*_EXACT` deny exact matches.
PLACEHOLDER_PASSWORD_DENY_PREFIX: tuple[str, ...] = ("changeme", "password")
PLACEHOLDER_PASSWORD_DENY_EXACT: tuple[str, ...] = (
    "admin",
    "test",
    "demo",
    "123456",
    "qwerty",
    "secret",
)


def is_placeholder_password(value: str | None) -> bool:
    """Check a candidate password against the placeholder deny-list."""
    if not value:
        return True
    lowered = value.strip().lower()
    if not lowered:
        return True
    if lowered in PLACEHOLDER_PASSWORD_DENY_EXACT:
        return True
    return any(
        lowered.startswith(prefix) for prefix in PLACEHOLDER_PASSWORD_DENY_PREFIX
    )


class Settings(BaseSettings):
    """Application settings read exclusively from environment variables."""

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = Field(alias="DATABASE_URL")
    jwt_secret: str = Field(alias="JWT_SECRET")
    wa_bsp_token: str = Field(default="", alias="WA_BSP_TOKEN")
    wa_phone_id: str = Field(default="", alias="WA_PHONE_ID")
    mp_access_token: str = Field(default="", alias="MP_ACCESS_TOKEN")
    slot_public_base_url: str = Field(
        default="http://localhost:8000", alias="SLOT_PUBLIC_BASE_URL"
    )
    reminder_t48h_hs: int = Field(default=48, alias="REMINDER_T48H_HS")
    reminder_t24h_hs: int = Field(default=24, alias="REMINDER_T24H_HS")
    default_cancel_anticip_hs: int = Field(
        default=24, alias="DEFAULT_CANCEL_ANTICIP_HS"
    )
    # C-03 auth lifetimes (D8): short access, week-long rotating refresh.
    jwt_access_minutes: int = Field(default=15, alias="JWT_ACCESS_MINUTES")
    jwt_refresh_days: int = Field(default=7, alias="JWT_REFRESH_DAYS")
    # Portal signing secret (D7/D8): separate domain from JWT_SECRET; falls
    # back with a warning so dev keeps working, CI fails in prod (see below).
    portal_secret: str = Field(default="", alias="PORTAL_SECRET")
    # Initial demo-admin password consumed ONLY by the C-03 seed rotation.
    admin_initial_password: str = Field(default="", alias="ADMIN_INITIAL_PASSWORD")
    app_env: str = Field(default="dev", alias="APP_ENV")
    # Login rate limit (D5): attempts per rolling window, keyed by IP+email.
    auth_rate_limit_per_minute: int = Field(
        default=5, alias="AUTH_RATE_LIMIT_PER_MINUTE"
    )
    auth_rate_limit_window_seconds: int = Field(
        default=60, alias="AUTH_RATE_LIMIT_WINDOW_SECONDS"
    )

    @property
    def portal_secret_value(self) -> str:
        """Effective portal secret (explicit value or JWT_SECRET fallback)."""
        if self.portal_secret:
            return self.portal_secret
        warnings.warn(
            "PORTAL_SECRET is not set; falling back to JWT_SECRET. "
            "Set a distinct PORTAL_SECRET (required in prod).",
            UserWarning,
            stacklevel=2,
        )
        return self.jwt_secret

    @property
    def portal_secret_configured(self) -> bool:
        """Whether PORTAL_SECRET was explicitly configured (no fallback)."""
        return bool(self.portal_secret)


def require_portal_secret_for_prod(settings: Settings) -> None:
    """CI gate (D8 risk): prod requires an explicit, distinct PORTAL_SECRET."""
    if settings.app_env.strip().lower() != "prod":
        return
    if not settings.portal_secret_configured:
        raise ValueError(
            "PORTAL_SECRET must be set explicitly when APP_ENV=prod "
            "(refusing JWT_SECRET fallback across signing domains)"
        )


def get_settings() -> Settings:
    """Build settings from the current environment (fail-fast on missing secrets)."""
    return Settings()  # type: ignore[call-arg]
