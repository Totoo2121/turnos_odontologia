"""C-03 auth HTTP seam: login / refresh / logout / me (D2, D5, D9).

- Refresh travels ONLY in an HttpOnly cookie (`Path=/api/auth`,
  `SameSite=Lax`, `Secure` in prod); the access token is returned in JSON.
- Failures are generic 401s (no user enumeration); login/refresh carry the
  in-process slowapi `5/minute` layer (D5) on top of the service-level
  5/60s IP+email budget that the spec scenarios pin down.
- Pydantic v2 validates every body; uniform errors flow through `AppError`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.auth_service import (
    AuthError,
    AuthService,
    LoginRateLimiter,
    RateLimitedError,
)
from app.infrastructure.auth_store import DbSessionStore, DbUserLookup
from app.shared.db import get_db
from app.shared.settings import get_settings

REFRESH_COOKIE = "refresh_token"
REFRESH_COOKIE_PATH = "/api/auth"

# D5: slowapi in-process coarse layer (per-IP). The exact spec budget
# (5/60s per IP+email) lives in the service limiter, which tests pin down.
limiter = Limiter(key_func=get_remote_address, headers_enabled=True)

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    """Login body: tenant slug scopes the credential (email is per-tenant)."""

    tenant_slug: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    """Access token (JSON); the refresh token travels in the cookie."""

    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    """Bearer identity (spec: sub, tenant_id, roles, email)."""

    sub: str
    tenant_id: str
    roles: list[str]
    email: str


_login_limiter: LoginRateLimiter | None = None


def get_login_limiter() -> LoginRateLimiter:
    """Process-wide service limiter (in-process per D5 risk note)."""
    global _login_limiter
    if _login_limiter is None:
        settings = get_settings()
        _login_limiter = LoginRateLimiter(
            attempts=settings.auth_rate_limit_per_minute,
            window_seconds=settings.auth_rate_limit_window_seconds,
        )
    return _login_limiter


async def get_auth_service(
    session: AsyncSession = Depends(get_db),
) -> AuthService:
    """Production service: DB adapters over the request session."""
    settings = get_settings()
    return AuthService(
        jwt_secret=settings.jwt_secret,
        access_minutes=settings.jwt_access_minutes,
        refresh_days=settings.jwt_refresh_days,
        users=DbUserLookup(session),
        sessions=DbSessionStore(session),
        limiter=get_login_limiter(),
        secure_cookies=settings.app_env.strip().lower() == "prod",
    )


def configure_rate_limiting(app) -> None:  # type: ignore[no-untyped-def]
    """Mount the limiter state + 429 handler (called by main and test rigs)."""

    async def _rate_limit_handler(
        request: Request, exc: RateLimitExceeded
    ) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"detail": "too many login attempts"},
            headers={"Retry-After": "60"},
        )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)  # type: ignore[arg-type]


def _set_refresh_cookie(
    response: Response, refresh_token: str, *, secure: bool, max_age: int
) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
        max_age=max_age,
    )


def _clear_refresh_cookie(response: Response, *, secure: bool) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=secure,
        samesite="lax",
    )


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthError()
    return token.strip()


@router.post("/auth/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Verify credential → access (JSON) + refresh (HttpOnly cookie)."""
    client_ip = request.client.host if request.client else "unknown"
    try:
        pair = await service.login(
            tenant_slug=body.tenant_slug,
            email=body.email,
            password=body.password,
            client_key=client_ip,
        )
    except RateLimitedError as exc:
        return JSONResponse(  # type: ignore[return-value]
            status_code=429,
            content={"detail": "too many login attempts"},
            headers={"Retry-After": str(exc.retry_after_seconds)},
        )
    _set_refresh_cookie(
        response,
        pair.refresh_token,
        secure=service.secure_cookies,
        max_age=service.refresh_days * 24 * 3600,
    )
    return TokenResponse(access_token=pair.access_token)


@router.post("/auth/refresh", response_model=TokenResponse)
@limiter.limit("5/minute")
async def refresh(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Rotate the cookie refresh → new pair (reuse kills the family)."""
    presented = request.cookies.get(REFRESH_COOKIE)
    if not presented:
        raise AuthError()
    pair = await service.refresh(presented)
    _set_refresh_cookie(
        response,
        pair.refresh_token,
        secure=service.secure_cookies,
        max_age=service.refresh_days * 24 * 3600,
    )
    return TokenResponse(access_token=pair.access_token)


@router.post("/auth/logout")
async def logout(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    """Revoke the presented access token + clear the refresh cookie."""
    await service.logout(_bearer_token(request))
    _clear_refresh_cookie(response, secure=service.secure_cookies)
    return {"status": "ok"}


@router.get("/auth/me", response_model=MeResponse)
async def me(
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> MeResponse:
    """Bearer identity: sub, tenant_id, roles, email."""
    principal = await service.me(_bearer_token(request))
    return MeResponse(
        sub=principal.sub,
        tenant_id=str(principal.tenant_id),
        roles=list(principal.roles),
        email=principal.email,
    )
