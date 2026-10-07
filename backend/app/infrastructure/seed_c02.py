"""C-02 minimal seed (D9): 1 fictitious demo tenant + 4 roles + 1 admin.

Idempotent (upsert by natural keys; safe to re-run). All values are synthetic
and fictitious (``.invalid`` mail domain, ``0000`` phone). Runs as the
migration/seed privileged role (BYPASSRLS per D1); tenant-scoped writes pin
``app.tenant_id`` defensively so they also succeed under RLS enforcement.

TODO(C-03): replace ``PASSWORD_UNSET_MARKER`` with a real password hash
(argon2id vs bcrypt lives in C-03) and harden ``usuario.password_hash`` to
NOT NULL. The marker below never authenticates against anything.
"""

import asyncio
import uuid

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import (
    PASSWORD_UNSET_MARKER,
    ROLE_NAMES,
    Rol,
    Sucursal,  # noqa: F401  (imported so metadata is complete for seed users)
    Tenant,
    UserRol,
    Usuario,
)

DEMO_SLUG = "demo-ficticia"
DEMO_TENANT_NAME = "Clinica Demo (ficticia)"
ADMIN_EMAIL = "admin@demo-ficticia.invalid"
ADMIN_NAME = "Admin Demo (ficticio)"

ROLE_DESCRIPTIONS = {
    "propietario": "Duenio del tenant demo (ficticio)",
    "odontologo": "Profesional odontologico (ficticio)",
    "recepcion": "Recepcion y agenda (ficticio)",
    "asistente": "Asistencia en consultorio (ficticio)",
}


class SeedError(RuntimeError):
    """Seed cannot proceed (fail-closed, e.g. unprivileged role without GUC)."""


async def _pin_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Pin the tenant GUC transaction-locally for RLS-scoped writes."""
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": str(tenant_id)},
    )


async def _find_tenant(session: AsyncSession, slug: str) -> Tenant | None:
    """Find a tenant by reservation slug (None when absent)."""
    try:
        return (
            await session.execute(select(Tenant).where(Tenant.slug_reserva == slug))
        ).scalar_one_or_none()
    except DBAPIError as exc:
        if "app.tenant_id" in str(exc):
            raise SeedError(
                "seed needs a BYPASSRLS/migration role for the first run "
                "(tenant lookup without app.tenant_id is denied fail-closed)"
            ) from exc
        raise


async def seed_c02(session: AsyncSession) -> dict[str, int]:
    """Create the demo tenant, role catalog and admin owner (idempotent).

    Returns a summary with the resulting counts (tenants/roles/admins).
    Committing is the caller's job (lets tests and CLIs bracket the txn).
    """
    # 1. Global role catalog (no RLS, no tenant): upsert by nombre.
    existing_roles = {
        row.nombre for row in (await session.execute(select(Rol))).scalars().all()
    }
    for name in ROLE_NAMES:
        if name not in existing_roles:
            session.add(Rol(nombre=name, descripcion=ROLE_DESCRIPTIONS[name]))
    await session.flush()

    # 2. Demo tenant (upsert by slug_reserva).
    tenant = await _find_tenant(session, DEMO_SLUG)
    if tenant is None:
        tenant = Tenant(
            id=uuid.uuid4(), slug_reserva=DEMO_SLUG, nombre=DEMO_TENANT_NAME
        )
        await _pin_tenant(session, tenant.id)
        session.add(tenant)
        await session.flush()
    tenant_id = tenant.id
    await _pin_tenant(session, tenant_id)

    # 3. Admin owner (upsert by (tenant_id, email)) + propietario link.
    admin = (
        await session.execute(
            select(Usuario).where(
                Usuario.tenant_id == tenant_id, Usuario.email == ADMIN_EMAIL
            )
        )
    ).scalar_one_or_none()
    if admin is None:
        admin = Usuario(
            tenant_id=tenant_id,
            email=ADMIN_EMAIL,
            nombre=ADMIN_NAME,
            # TODO(C-03): real hash + NOT NULL; this marker never authenticates.
            password_hash=PASSWORD_UNSET_MARKER,
        )
        session.add(admin)
        await session.flush()
    owner_role = (
        await session.execute(select(Rol).where(Rol.nombre == "propietario"))
    ).scalar_one()
    link = (
        await session.execute(
            select(UserRol).where(
                UserRol.usuario_id == admin.id, UserRol.rol_id == owner_role.id
            )
        )
    ).scalar_one_or_none()
    if link is None:
        session.add(
            UserRol(usuario_id=admin.id, rol_id=owner_role.id, tenant_id=tenant_id)
        )
        await session.flush()

    role_count = len((await session.execute(select(Rol))).scalars().all())
    return {"tenants": 1, "roles": role_count, "admins": 1}


async def main() -> None:
    """CLI entry: ``python -m app.infrastructure.seed_c02`` from backend/."""
    from app.shared.db import create_engine_from_settings, create_session_factory

    engine = create_engine_from_settings()
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            summary = await seed_c02(session)
            await session.commit()
        print(f"seed_c02 ok: {summary} (all values fictitious)")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
