"""C-03 auth dependencies (D4, D9, D10).

`PUBLIC_PATHS` is the declarative allowlist consumed by the auth seam:
health (no JWT by C-01 design), the turnero + portal public surfaces, and
the provider-signed webhooks — whose captcha/signature guards land in
C-08/C-10/C-11 (D9: declared here, not implemented).

`get_current_principal` validates the Bearer `type=access` token through the
`AuthService` (signature + expiry + type + denylist) and returns a
`Principal` whose `tenant_id` comes ONLY from the token — never from
body/query/path (D4). `tenant_session` pins that tenant into the request
transaction (`SET LOCAL app.tenant_id`, reusing the C-02 `UnitOfWork` GUC
shape) so RLS enforces the same boundary underneath. The composable RBAC
guards (`require_role`, `require_any`, `require_owner_or_treating`, D10)
answer 401/403/404 uniformly via `AppError`.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_auth_service
from app.application.auth_service import AuthError, AuthService, Principal
from app.application.rbac import may_access_hce as _may_access_hce
from app.shared.db import get_db
from app.shared.exceptions import AppError

# Re-exported for consumers that only depend on `api.deps` (D10 seam).
may_access_hce = _may_access_hce

__all__ = [
    "PUBLIC_PATHS",
    "is_public_path",
    "get_auth_service",
    "get_current_principal",
    "tenant_session",
    "require_role",
    "require_any",
    "require_owner_or_treating",
    "may_access_hce",
]

# (method, path-pattern): `{name}` matches one segment, trailing `/*` matches
# a prefix. Everything else requires a validated `type=access` JWT.
PUBLIC_PATHS: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/health"),
        ("GET", "/reservar/{slug}"),
        ("GET", "/p/{token}"),
        ("POST", "/webhooks/mercadopago"),
        ("POST", "/webhooks/whatsapp"),
    }
)


def _pattern_matches(pattern: str, path: str) -> bool:
    if pattern.endswith("/*"):
        prefix = pattern[:-2]
        return path == prefix or path.startswith(prefix + "/")
    pattern_parts = pattern.split("/")
    path_parts = path.split("/")
    if len(pattern_parts) != len(path_parts):
        return False
    return all(
        part.startswith("{") and part.endswith("}") or part == actual
        for part, actual in zip(pattern_parts, path_parts)
    )


def is_public_path(method: str, path: str) -> bool:
    """Check whether a request bypasses JWT (exact or templated match)."""
    wanted = method.strip().upper()
    for allowed_method, pattern in PUBLIC_PATHS:
        if allowed_method == wanted and _pattern_matches(pattern, path):
            return True
    return False


def _bearer_token(request: Request) -> str:
    """Extract the Bearer token (uniform 401 on missing/malformed)."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthError()
    return token.strip()


async def get_current_principal(
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> Principal:
    """Validate the Bearer access token → Principal (D4).

    The `tenant_id` is taken from the verified token claims only: a forged
    signature (including an adulterated `tenant_id`) fails here with 401
    before any store is touched.
    """
    return await service.validate_access(_bearer_token(request))


async def tenant_session(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db),
) -> AsyncSession:
    """Pin the token tenant into this transaction (D4 → UnitOfWork/SET LOCAL).

    Consumers build repositories from the returned session; the tenant NEVER
    comes from client params. Without this pin the RLS policies fail closed.
    """
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(principal.tenant_id)},
    )
    return session


def require_role(role: str) -> Callable[..., object]:
    """Guard: the principal must hold `role`, else uniform 403 (D10)."""

    async def guard(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        if role not in principal.roles:
            raise AppError("forbidden", 403)
        return principal

    return guard


def require_any(*roles: str) -> Callable[..., object]:
    """Guard: the principal must hold at least one role, else 403 (D10)."""

    async def guard(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        if not any(role in principal.roles for role in roles):
            raise AppError("forbidden", 403)
        return principal

    return guard


def require_owner_or_treating(
    *, allow_treating_or_derived: bool = False
) -> Callable[..., object]:
    """HCE guard: propietario always; others need treating/derivation (D10).

    Until C-12 provides the treating/derivation tables, callers leave the
    flag False and non-owners deny fail-closed — answered as 404 (treated as
    inexistente, RN-SE-02) so denied callers learn nothing about the record.
    """

    async def guard(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        if not _may_access_hce(
            tuple(principal.roles),
            is_owner_treating_or_derived=allow_treating_or_derived,
        ):
            raise AppError("not found", 404)
        return principal

    return guard
