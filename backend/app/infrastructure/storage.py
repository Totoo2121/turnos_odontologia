"""C-13 private storage for clinical attachments (port + local/memory).

No cloud SDK is imported in this change: ``memory`` backs tests and ``local``
backs dev/CI. Both issue HMAC-SHA256 signed, expiring URLs bound to the
tenant, so possession of a URL is a short-lived capability and a tampered
key/tenant/expiry fails closed. An S3/GCS adapter can land behind the same
``StoragePort`` without touching the application service.
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import hashlib
import hmac
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from app.shared.exceptions import AppError
from app.shared.settings import get_settings

ALGORITHM = "hmac-sha256"


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


@dataclass(frozen=True)
class SignedURL:
    """Signed, expiring download URL for one storage key."""

    url: str
    expires_at: datetime.datetime


class SignedURLSigner:
    """HMAC-SHA256 signer for capability URLs (key + tenant + expiry)."""

    def __init__(
        self,
        secret: str,
        *,
        ttl_seg: int = 300,
        base_url: str = "",
    ) -> None:
        if not secret:
            raise ValueError("storage signer requires a non-empty secret")
        self._secret = secret.encode("utf-8")
        self.ttl_seg = ttl_seg
        self.base_url = base_url.rstrip("/")

    def _signature(self, key: str, tenant_id: str, exp: int) -> str:
        message = f"{key}|{tenant_id}|{exp}".encode()
        digest = hmac.new(self._secret, message, hashlib.sha256).digest()
        return _b64encode(digest)

    def sign(
        self,
        key: str,
        tenant_id: uuid.UUID,
        *,
        ttl_seg: int | None = None,
    ) -> SignedURL:
        ttl = self.ttl_seg if ttl_seg is None else ttl_seg
        if ttl <= 0:
            raise ValueError("ttl_seg must be positive")
        expires_at = _now() + datetime.timedelta(seconds=ttl)
        exp = int(expires_at.timestamp())
        token = f"{exp}.{tenant_id}.{self._signature(key, str(tenant_id), exp)}"
        path = f"/api/storage/{quote(key, safe='/')}?token={token}"
        return SignedURL(url=f"{self.base_url}{path}", expires_at=expires_at)

    def verify(self, key: str, token: str) -> uuid.UUID:
        """Return the tenant bound to a valid token, else raise 403."""
        try:
            exp_raw, tenant_raw, signature = token.split(".", 2)
            exp = int(exp_raw)
            tenant_id = uuid.UUID(tenant_raw)
        except (ValueError, AttributeError):
            raise AppError("url firmada invalida", 403) from None
        expected = self._signature(key, str(tenant_id), exp)
        if not hmac.compare_digest(signature, expected):
            raise AppError("url firmada invalida", 403)
        if exp < int(_now().timestamp()):
            raise AppError("url firmada expirada", 403)
        return tenant_id


class StoragePort(Protocol):
    """Persistence seam for private bytes."""

    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def get(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...

    def signed_url(
        self,
        key: str,
        tenant_id: uuid.UUID,
        *,
        ttl_seg: int | None = None,
    ) -> SignedURL: ...

    def verify_token(self, key: str, token: str) -> uuid.UUID: ...


class InMemoryStorage:
    """Dict-backed storage for tests (no disk, no network)."""

    def __init__(self, signer: SignedURLSigner) -> None:
        self._signer = signer
        self._objects: dict[str, tuple[bytes, str]] = {}

    @property
    def objects(self) -> dict[str, tuple[bytes, str]]:
        return self._objects

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self._objects[key] = (data, content_type)

    async def get(self, key: str) -> bytes:
        try:
            return self._objects[key][0]
        except KeyError:
            raise AppError("objeto no encontrado", 404) from None

    async def delete(self, key: str) -> None:
        self._objects.pop(key, None)

    def signed_url(
        self,
        key: str,
        tenant_id: uuid.UUID,
        *,
        ttl_seg: int | None = None,
    ) -> SignedURL:
        return self._signer.sign(key, tenant_id, ttl_seg=ttl_seg)

    def verify_token(self, key: str, token: str) -> uuid.UUID:
        return self._signer.verify(key, token)


class LocalFilesystemStorage:
    """Private directory storage for dev/CI (never served statically)."""

    def __init__(self, root: str | Path, signer: SignedURLSigner) -> None:
        self._root = Path(root).resolve()
        self._signer = signer

    @property
    def root(self) -> Path:
        return self._root

    def _path(self, key: str) -> Path:
        if not key or key.startswith("/") or ".." in Path(key).parts:
            raise AppError("storage key invalida", 400)
        candidate = (self._root / key).resolve()
        if not candidate.is_relative_to(self._root):
            raise AppError("storage key invalida", 400)
        return candidate

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(self._write, path, data)

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError:
            raise AppError("objeto no encontrado", 404) from None

    async def delete(self, key: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.unlink, True)

    def signed_url(
        self,
        key: str,
        tenant_id: uuid.UUID,
        *,
        ttl_seg: int | None = None,
    ) -> SignedURL:
        self._path(key)
        return self._signer.sign(key, tenant_id, ttl_seg=ttl_seg)

    def verify_token(self, key: str, token: str) -> uuid.UUID:
        return self._signer.verify(key, token)


def build_storage() -> StoragePort:
    """Build the configured storage backend (fail fast on unknown values)."""
    settings = get_settings()
    backend = settings.storage_backend.strip().lower()
    base_url = settings.public_base_url or settings.slot_public_base_url
    signer = SignedURLSigner(
        settings.storage_signing_secret_value,
        ttl_seg=settings.storage_signed_url_ttl_seg,
        base_url=base_url,
    )
    if backend == "memory":
        return InMemoryStorage(signer)
    if backend == "local":
        return LocalFilesystemStorage(settings.storage_local_root, signer)
    raise ValueError(
        f"unsupported STORAGE_BACKEND={settings.storage_backend!r} "
        "(supported: memory, local; cloud adapters are a planned extension)"
    )
