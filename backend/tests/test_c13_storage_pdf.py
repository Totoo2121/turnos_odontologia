"""C-13 tasks 2.1/2.2/2.3: storage signer, local backend and PDF writer."""

from __future__ import annotations

import asyncio
import datetime
import os
import uuid
from pathlib import Path

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest

from app.infrastructure.pdf import SimplePdfWriter
from app.infrastructure.storage import (
    InMemoryStorage,
    LocalFilesystemStorage,
    SignedURLSigner,
)
from app.shared.exceptions import AppError

SECRET = "fictitious-storage-secret-not-real"


def _signer(ttl_seg: int = 300) -> SignedURLSigner:
    return SignedURLSigner(SECRET, ttl_seg=ttl_seg, base_url="http://testserver")


def test_signed_url_round_trip_returns_tenant() -> None:
    """WHEN a URL is signed THEN verify returns the bound tenant."""
    signer = _signer()
    tenant = uuid.uuid4()
    signed = signer.sign("a/b/c", tenant)
    assert signed.url.startswith("http://testserver/api/storage/a/b/c?token=")
    assert signer.verify("a/b/c", signed.url.split("token=", 1)[1]) == tenant


def test_tampered_token_is_rejected() -> None:
    """WHEN the signature is altered THEN 403."""
    signer = _signer()
    signed = signer.sign("a/b/c", uuid.uuid4())
    token = signed.url.split("token=", 1)[1]
    with pytest.raises(AppError) as exc:
        signer.verify("a/b/c", token[:-2] + "xx")
    assert exc.value.status_code == 403


def test_token_is_bound_to_key() -> None:
    """WHEN a valid token is used for another key THEN 403."""
    signer = _signer()
    signed = signer.sign("a/b/c", uuid.uuid4())
    token = signed.url.split("token=", 1)[1]
    with pytest.raises(AppError) as exc:
        signer.verify("a/b/otro", token)
    assert exc.value.status_code == 403


def test_expired_token_is_rejected() -> None:
    """WHEN exp is in the past THEN 403."""
    signer = _signer()
    tenant = uuid.uuid4()
    past = int(
        (datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=5))
        .timestamp()
    )
    token = f"{past}.{tenant}.{signer._signature('a/b/c', str(tenant), past)}"
    with pytest.raises(AppError) as exc:
        signer.verify("a/b/c", token)
    assert exc.value.status_code == 403


def test_memory_storage_put_get_delete() -> None:
    """WHEN bytes are stored THEN they round-trip and can be deleted."""
    storage = InMemoryStorage(_signer())

    async def scenario() -> None:
        await storage.put("k", b"rx-ficticia", "image/jpeg")
        assert await storage.get("k") == b"rx-ficticia"
        await storage.delete("k")
        with pytest.raises(AppError):
            await storage.get("k")

    asyncio.run(scenario())


def test_local_storage_round_trip(tmp_path: Path) -> None:
    """WHEN local storage writes THEN bytes land inside the root."""
    storage = LocalFilesystemStorage(tmp_path, _signer())

    async def scenario() -> None:
        await storage.put("t/h/file.bin", b"contenido", "application/pdf")
        assert (tmp_path / "t/h/file.bin").read_bytes() == b"contenido"
        assert await storage.get("t/h/file.bin") == b"contenido"
        await storage.delete("t/h/file.bin")

    asyncio.run(scenario())


def test_local_storage_rejects_traversal(tmp_path: Path) -> None:
    """WHEN the key escapes the root THEN 400."""
    storage = LocalFilesystemStorage(tmp_path, _signer())

    async def scenario() -> None:
        with pytest.raises(AppError) as exc:
            await storage.put("../fuera.bin", b"x", "application/pdf")
        assert exc.value.status_code == 400

    asyncio.run(scenario())


def test_pdf_is_deterministic_and_contains_hash() -> None:
    """WHEN the same lines render twice THEN bytes and embedded hash match."""
    writer = SimplePdfWriter()
    lines = ["CONSENTIMIENTO INFORMADO", "Hash: " + "a" * 64]
    first = writer.render(lines)
    second = writer.render(lines)
    assert first == second
    assert first.startswith(b"%PDF-1.4")
    assert first.rstrip().endswith(b"%%EOF")
    assert b"a" * 64 in first


def test_pdf_escapes_parentheses_and_backslashes() -> None:
    """WHEN text has PDF metacharacters THEN rendering stays valid."""
    pdf = SimplePdfWriter().render(["firma (ficticia) \\ prueba"])
    assert pdf.startswith(b"%PDF-1.4")
    assert b"\\(" in pdf and b"\\)" in pdf
