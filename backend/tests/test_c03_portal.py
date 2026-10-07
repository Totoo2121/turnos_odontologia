"""C-03 portal token tests (task 6.1) — RED first.

Single-turno portal JWTs (`type=portal`, D7): a valid token authorizes only
its own turno, while expired / revoked / foreign / tampered tokens are
rejected without exposing data. Revocation lives in the `portal_token` row
mirror (in-memory here; the DB adapter is exercised in CI with Postgres).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

TENANT_ID = uuid.uuid4()
OTHER_TENANT_ID = uuid.uuid4()
TURNO_ID = uuid.uuid4()
OTHER_TURNO_ID = uuid.uuid4()
PORTAL_SECRET = "fictitious-portal-secret-for-tests-only"
JWT_SECRET = "fictitious-jwt-secret-for-tests-only"


def _service() -> object:
    from app.application.portal_service import MemoryPortalStore, PortalService

    return PortalService(portal_secret=PORTAL_SECRET, store=MemoryPortalStore())


def _issue(service: object, **overrides: object) -> str:
    now = datetime.now(UTC)
    kwargs: dict[str, object] = {
        "turno_id": TURNO_ID,
        "tenant_id": TENANT_ID,
        "turno_inicio": now + timedelta(hours=2),
        "now": now,
    }
    kwargs.update(overrides)
    return service.issue(**kwargs)  # type: ignore[operator]


@pytest.mark.asyncio
async def test_valid_portal_token_authorizes_only_its_turno() -> None:
    """WHEN portal token vigente THEN validates to its turno+tenant."""
    service = _service()
    token = _issue(service)
    record = await service.validate(  # type: ignore[operator]
        token, expected_turno_id=TURNO_ID, expected_tenant_id=TENANT_ID
    )
    assert record.turno_id == TURNO_ID
    assert record.tenant_id == TENANT_ID


@pytest.mark.asyncio
async def test_expired_portal_token_is_401() -> None:
    """WHEN turno started >24h ago THEN token expired → 401."""
    from app.application.portal_service import PortalError

    service = _service()
    token = _issue(service, turno_inicio=datetime.now(UTC) - timedelta(hours=25))
    with pytest.raises(PortalError) as exc_info:
        await service.validate(token)  # type: ignore[operator]
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_revoked_portal_token_is_404() -> None:
    """WHEN portal row revoked (turno cancelado) THEN 404, no data."""
    from app.application.portal_service import PortalError

    service = _service()
    token = _issue(service)
    assert await service.revoke(token) is True  # type: ignore[operator]
    with pytest.raises(PortalError) as exc_info:
        await service.validate(token)  # type: ignore[operator]
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_foreign_turno_or_tenant_is_404() -> None:
    """WHEN token used for another turno/tenant THEN 404 without leak."""
    from app.application.portal_service import PortalError

    service = _service()
    token = _issue(service)
    for kwargs in (
        {"expected_turno_id": OTHER_TURNO_ID, "expected_tenant_id": TENANT_ID},
        {"expected_turno_id": TURNO_ID, "expected_tenant_id": OTHER_TENANT_ID},
    ):
        with pytest.raises(PortalError) as exc_info:
            await service.validate(token, **kwargs)  # type: ignore[operator]
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_tampered_portal_token_is_401() -> None:
    """WHEN signature adulterada THEN 401 before any lookup."""
    from app.application.portal_service import PortalError

    service = _service()
    token = _issue(service)
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    with pytest.raises(PortalError) as exc_info:
        await service.validate(tampered)  # type: ignore[operator]
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_access_token_is_not_a_portal_token() -> None:
    """WHEN access JWT presented as portal THEN 401 (type separation, D7)."""
    from app.application.portal_service import PortalError
    from app.infrastructure.security import create_access_token

    service = _service()
    access = create_access_token(
        sub="user-ficticio",
        tenant_id=str(TENANT_ID),
        roles=["recepcion"],
        email="recepcion@demo-ficticia.invalid",
        secret=JWT_SECRET,
    )
    with pytest.raises(PortalError) as exc_info:
        await service.validate(access)  # type: ignore[operator]
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_portal_expiry_caps_at_turno_plus_24h() -> None:
    """WHEN turno far future THEN expiry is min(turno+24h, now+90d) (D7)."""
    service = _service()
    now = datetime.now(UTC)
    token = _issue(service, turno_inicio=now + timedelta(days=200), now=now)
    record = await service.validate(token)  # type: ignore[operator]
    assert record.expires_at <= now + timedelta(days=90)
    assert record.expires_at > now + timedelta(days=89)
