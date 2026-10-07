"""Secrets-hygiene test (C-01 tasks 2.2 + spec: no secrets in repo)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REQUIRED_KEYS = [
    "DATABASE_URL",
    "JWT_SECRET",
    "WA_BSP_TOKEN",
    "WA_PHONE_ID",
    "MP_ACCESS_TOKEN",
    "SLOT_PUBLIC_BASE_URL",
    "REMINDER_T48H_HS",
    "REMINDER_T24H_HS",
    "DEFAULT_CANCEL_ANTICIP_HS",
]

FORBIDDEN_FRAGMENTS = ["sk-", "ya29.", "postgresql://real", "prod-secret"]


def _env_example() -> Path:
    return ROOT / ".env.example"


def test_env_example_documents_all_nine_vars() -> None:
    """WHEN .env.example inspected THEN all 9 vars are documented."""
    content = _env_example().read_text(encoding="utf-8")
    for key in REQUIRED_KEYS:
        assert key in content, f"missing documented var: {key}"


def test_env_example_has_placeholders_only() -> None:
    """WHEN .env.example inspected THEN secrets are placeholders, never real."""
    content = _env_example().read_text(encoding="utf-8")
    assert "CHANGEME" in content or "fictitious" in content
    lowered = content.lower()
    for fragment in FORBIDDEN_FRAGMENTS:
        assert fragment not in lowered, f"real-looking secret: {fragment}"
