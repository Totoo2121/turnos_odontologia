"""C-03 credential rotation (D1): marker → real argon2id hash.

Runs AFTER Migración 002 (which locked the C-02 ``!UNSET-*`` marker into the
fail-closed ``!LOCKED-C03-MIGRATED*`` value and hardened the column to
NOT NULL). Reads the initial demo-admin password from
``ADMIN_INITIAL_PASSWORD`` only — never from code — refusing placeholders
via the settings deny-list. Idempotent: safe to re-run (rotation is skipped
when the stored hash already verifies). All seed values are fictitious.
"""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure import seed_c02
from app.infrastructure.security import hash_password, verify_password
from app.shared.settings import is_placeholder_password


class SeedError(RuntimeError):
    """Seed rotation cannot proceed fail-closed (missing/placeholder secret)."""


def resolve_admin_password(explicit: str | None = None) -> str:
    """Resolve the seed password from param/env, refusing missing/placeholder."""
    candidate = (
        explicit
        if explicit is not None
        else os.environ.get("ADMIN_INITIAL_PASSWORD", "")
    )
    if not candidate:
        raise SeedError(
            "ADMIN_INITIAL_PASSWORD is not set (refusing to seed an unusable "
            "credential; copy .env.example and set a strong fictitious value)"
        )
    if is_placeholder_password(candidate):
        raise SeedError(
            "ADMIN_INITIAL_PASSWORD looks like a placeholder (deny-listed; "
            "choose a strong fictitious value instead)"
        )
    return candidate


async def rotate_admin_password(
    session: AsyncSession, password: str | None = None
) -> dict[str, int | bool]:
    """Ensure C-02 base rows exist and the demo admin carries a real hash.

    Returns ``{"tenants": 1, "roles": N, "admins": 1, "rotated": bool}``.
    Committing is the caller's job (lets tests and CLIs bracket the txn).
    """
    resolved = resolve_admin_password(password)
    summary = await seed_c02.seed_c02(session)
    await session.flush()
    admin = (
        await session.execute(
            select(seed_c02.Usuario).where(
                seed_c02.Usuario.email == seed_c02.ADMIN_EMAIL
            )
        )
    ).scalar_one()
    if admin.password_hash and verify_password(admin.password_hash, resolved):
        return {"tenants": 1, "roles": summary["roles"], "admins": 1, "rotated": False}
    admin.password_hash = hash_password(resolved)
    await session.flush()
    return {"tenants": 1, "roles": summary["roles"], "admins": 1, "rotated": True}


async def main() -> None:
    """CLI entry: ``python -m app.infrastructure.seed_c03`` from backend/."""
    from app.shared.db import create_engine_from_settings, create_session_factory

    engine = create_engine_from_settings()
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            summary = await rotate_admin_password(session)
            await session.commit()
        print(f"seed_c03 ok: {summary} (all values fictitious)")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
