"""C-13 task 2.1: storage settings, signer fallback and prod gate."""

from __future__ import annotations

import os
import uuid
import warnings

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest

from app.infrastructure.storage import (
    InMemoryStorage,
    LocalFilesystemStorage,
    build_storage,
)
from app.shared.settings import Settings, require_storage_secret_for_prod

BASE_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db",
    "JWT_SECRET": "fictitious-test-secret-not-real",
}
C13_VARS = (
    "APP_ENV",
    "STORAGE_BACKEND",
    "STORAGE_LOCAL_ROOT",
    "STORAGE_SIGNED_URL_TTL_SEG",
    "STORAGE_SIGNING_SECRET",
    "PUBLIC_BASE_URL",
    "SLOT_PUBLIC_BASE_URL",
    "ADJUNTO_MAX_BYTES",
    "ADJUNTO_MIME_PERMITIDOS",
)


def _settings(monkeypatch: pytest.MonkeyPatch, **extra: str) -> Settings:
    for var in C13_VARS:
        monkeypatch.delenv(var, raising=False)
    for key, value in {**BASE_ENV, **extra}.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_storage_defaults_are_private_and_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN nothing is configured THEN local storage, 300 s TTL, 10 MiB cap."""
    settings = _settings(monkeypatch)
    assert settings.storage_backend == "local"
    assert settings.storage_local_root == "var/storage"
    assert settings.storage_signed_url_ttl_seg == 300
    assert settings.storage_signing_secret == ""
    assert settings.adjunto_max_bytes == 10 * 1024 * 1024
    assert settings.mime_permitidos == (
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/pdf",
    )


def test_mime_allowlist_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    """WHEN the allowlist has blanks/case THEN it parses cleanly."""
    settings = _settings(
        monkeypatch,
        ADJUNTO_MIME_PERMITIDOS=" image/JPEG , ,application/pdf , ",
    )
    assert settings.mime_permitidos == ("image/jpeg", "application/pdf")


def test_storage_secret_falls_back_with_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN STORAGE_SIGNING_SECRET is missing THEN JWT_SECRET + warning."""
    settings = _settings(monkeypatch)
    with pytest.warns(UserWarning, match="STORAGE_SIGNING_SECRET"):
        assert (
            settings.storage_signing_secret_value
            == "fictitious-test-secret-not-real"
        )


def test_storage_secret_explicit_no_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN STORAGE_SIGNING_SECRET is set THEN it is used as-is."""
    settings = _settings(
        monkeypatch, STORAGE_SIGNING_SECRET="fictitious-storage-secret"
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert settings.storage_signing_secret_value == "fictitious-storage-secret"


def test_prod_without_storage_secret_fails_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN APP_ENV=prod without STORAGE_SIGNING_SECRET THEN the gate raises."""
    settings = _settings(monkeypatch, APP_ENV="prod")
    with pytest.raises(ValueError, match="STORAGE_SIGNING_SECRET"):
        require_storage_secret_for_prod(settings)


def test_prod_with_storage_secret_passes_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN APP_ENV=prod with STORAGE_SIGNING_SECRET THEN the gate passes."""
    settings = _settings(
        monkeypatch, APP_ENV="prod", STORAGE_SIGNING_SECRET="fictitious-secret"
    )
    require_storage_secret_for_prod(settings)  # must not raise


def test_dev_does_not_require_storage_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN APP_ENV is not prod THEN the gate is a no-op."""
    settings = _settings(monkeypatch, APP_ENV="dev")
    require_storage_secret_for_prod(settings)  # must not raise


def test_build_storage_selects_the_configured_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN STORAGE_BACKEND is memory/local THEN the right adapter is built."""
    import app.infrastructure.storage as storage_module

    memory = _settings(
        monkeypatch,
        STORAGE_BACKEND="memory",
        STORAGE_SIGNING_SECRET="fictitious-secret",
    )
    monkeypatch.setattr(storage_module, "get_settings", lambda: memory)
    assert isinstance(build_storage(), InMemoryStorage)

    local = _settings(
        monkeypatch,
        STORAGE_BACKEND="local",
        STORAGE_LOCAL_ROOT="var/storage-c13-test",
        STORAGE_SIGNING_SECRET="fictitious-secret",
        PUBLIC_BASE_URL="http://testserver",
    )
    monkeypatch.setattr(storage_module, "get_settings", lambda: local)
    backend = build_storage()
    assert isinstance(backend, LocalFilesystemStorage)
    assert str(backend.root).endswith("storage-c13-test")


def test_build_storage_rejects_unknown_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN STORAGE_BACKEND is unknown THEN fail fast (no silent fallback)."""
    import app.infrastructure.storage as storage_module

    settings = _settings(
        monkeypatch,
        STORAGE_BACKEND="s3",
        STORAGE_SIGNING_SECRET="fictitious-secret",
    )
    monkeypatch.setattr(storage_module, "get_settings", lambda: settings)
    with pytest.raises(ValueError, match="STORAGE_BACKEND"):
        build_storage()


def test_public_base_url_falls_back_to_slot_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN PUBLIC_BASE_URL is empty THEN signed URLs use SLOT_PUBLIC_BASE_URL."""
    import app.infrastructure.storage as storage_module

    settings = _settings(
        monkeypatch,
        STORAGE_BACKEND="memory",
        STORAGE_SIGNING_SECRET="fictitious-secret",
        SLOT_PUBLIC_BASE_URL="http://slot.testserver",
    )
    monkeypatch.setattr(storage_module, "get_settings", lambda: settings)
    backend = build_storage()
    signed = backend.signed_url("a/b", uuid.uuid4())
    assert signed.url.startswith("http://slot.testserver/api/storage/a/b?token=")
