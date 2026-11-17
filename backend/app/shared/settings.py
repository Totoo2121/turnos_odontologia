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
    mp_webhook_secret: str = Field(default="", alias="MP_WEBHOOK_SECRET")
    # C-11 WhatsApp webhook signature + SMTP fallback (secrets empty = stubbed).
    whatsapp_webhook_secret: str = Field(
        default="", alias="WHATSAPP_WEBHOOK_SECRET"
    )
    smtp_host: str = Field(default="localhost", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="no-reply@turnos.invalid", alias="SMTP_FROM")
    confirmation_threshold_hs: int = Field(
        default=24, alias="CONFIRMATION_THRESHOLD_HS"
    )
    recall_ausente_dias: int = Field(default=7, alias="RECALL_AUSENTE_DIAS")
    notif_max_intentos: int = Field(default=3, alias="NOTIF_MAX_INTENTOS")
    notif_backoff_base_s: float = Field(default=0.5, alias="NOTIF_BACKOFF_BASE_S")
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
    # C-13 private storage for clinical attachments (memory|local).
    storage_backend: str = Field(default="local", alias="STORAGE_BACKEND")
    storage_local_root: str = Field(
        default="var/storage", alias="STORAGE_LOCAL_ROOT"
    )
    storage_signed_url_ttl_seg: int = Field(
        default=300, alias="STORAGE_SIGNED_URL_TTL_SEG"
    )
    storage_signing_secret: str = Field(
        default="", alias="STORAGE_SIGNING_SECRET"
    )
    public_base_url: str = Field(default="", alias="PUBLIC_BASE_URL")
    adjunto_max_bytes: int = Field(
        default=10 * 1024 * 1024, alias="ADJUNTO_MAX_BYTES"
    )
    adjunto_mime_permitidos: str = Field(
        default=(
            "image/jpeg,image/png,image/webp,application/pdf"
        ),
        alias="ADJUNTO_MIME_PERMITIDOS",
    )
    # C-14: default validity window for a new treatment quote (days).
    presupuesto_validez_dias: int = Field(
        default=30, gt=0, alias="PRESUPUESTO_VALIDEZ_DIAS"
    )
    # Portal signing secret (D7/D8): separate domain from JWT_SECRET; falls
    # back with a warning so dev keeps working, CI fails in prod (see below).
    portal_secret: str = Field(default="", alias="PORTAL_SECRET")
    # Initial demo-admin password consumed ONLY by the C-03 seed rotation.
    admin_initial_password: str = Field(default="", alias="ADMIN_INITIAL_PASSWORD")
    app_env: str = Field(default="dev", alias="APP_ENV")
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="CORS_ORIGINS",
    )
    # Login rate limit (D5): attempts per rolling window, keyed by IP+email.
    auth_rate_limit_per_minute: int = Field(
        default=5, alias="AUTH_RATE_LIMIT_PER_MINUTE"
    )
    auth_rate_limit_window_seconds: int = Field(
        default=60, alias="AUTH_RATE_LIMIT_WINDOW_SECONDS"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse the explicit comma-separated browser origin allowlist."""
        return [origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()]

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

    @property
    def storage_signing_secret_value(self) -> str:
        """Effective storage signer secret (explicit or JWT_SECRET fallback)."""
        if self.storage_signing_secret:
            return self.storage_signing_secret
        warnings.warn(
            "STORAGE_SIGNING_SECRET is not set; falling back to JWT_SECRET. "
            "Set a distinct STORAGE_SIGNING_SECRET (required in prod).",
            UserWarning,
            stacklevel=2,
        )
        return self.jwt_secret

    @property
    def storage_signing_secret_configured(self) -> bool:
        """Whether STORAGE_SIGNING_SECRET was explicitly configured."""
        return bool(self.storage_signing_secret)

    @property
    def mime_permitidos(self) -> tuple[str, ...]:
        """Parsed MIME allowlist for clinical attachments."""
        return tuple(
            value.strip().lower()
            for value in self.adjunto_mime_permitidos.split(",")
            if value.strip()
        )


def require_portal_secret_for_prod(settings: Settings) -> None:
    """CI gate (D8 risk): prod requires an explicit, distinct PORTAL_SECRET."""
    if settings.app_env.strip().lower() != "prod":
        return
    if not settings.portal_secret_configured:
        raise ValueError(
            "PORTAL_SECRET must be set explicitly when APP_ENV=prod "
            "(refusing JWT_SECRET fallback across signing domains)"
        )


def require_storage_secret_for_prod(settings: Settings) -> None:
    """Prod requires an explicit STORAGE_SIGNING_SECRET for signed URLs."""
    if settings.app_env.strip().lower() != "prod":
        return
    if not settings.storage_signing_secret_configured:
        raise ValueError(
            "STORAGE_SIGNING_SECRET must be set explicitly when APP_ENV=prod "
            "(refusing JWT_SECRET fallback for attachment URLs)"
        )


def get_settings() -> Settings:
    """Build settings from the current environment (fail-fast on missing secrets)."""
    return Settings()  # type: ignore[call-arg]
