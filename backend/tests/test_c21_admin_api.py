"""C-21: owner admin API contract with a tenant-bound fake DB session."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-c21-test-secret-not-real")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.api import admin as admin_api
from app.api import audit as audit_api
from app.api.deps import get_current_principal, tenant_session
from app.application.auth_service import Principal
from app.infrastructure.security import verify_password
from app.shared.exceptions import register_exception_handlers


class _AsyncContext:
    def __init__(self, value):  # type: ignore[no-untyped-def]
        self.value = value

    async def __aenter__(self):  # type: ignore[no-untyped-def]
        return self.value

    async def __aexit__(self, *_exc):  # type: ignore[no-untyped-def]
        return None


class FakeAdminSession:
    def __init__(self) -> None:
        self.tenant_id = uuid.uuid4()
        self.tenant = SimpleNamespace(
            id=self.tenant_id,
            nombre="Clínica Ficticia",
            slug_reserva="demo-ficticia",
            moneda="ARS",
        )
        self.role = SimpleNamespace(id=uuid.uuid4(), nombre="recepcion")
        self.users: list[SimpleNamespace] = []
        self.user_roles: list[object] = []
        self.duplicate = False
        self.scalar_calls = 0

    async def scalar(self, statement):  # type: ignore[no-untyped-def]
        self.scalar_calls += 1
        entity = statement.column_descriptions[0]["entity"]
        if entity is admin_api.Tenant:
            return self.tenant
        if entity is admin_api.Rol:
            return self.role
        return None

    async def execute(self, _statement):  # type: ignore[no-untyped-def]
        self.last_statement = _statement
        return SimpleNamespace(
            all=lambda: [(user, role) for user, role in getattr(self, "rows", [])]
        )

    def add(self, value):  # type: ignore[no-untyped-def]
        if isinstance(value, admin_api.Usuario):
            self.users.append(value)
        else:
            self.user_roles.append(value)

    async def flush(self) -> None:
        if self.duplicate:
            raise IntegrityError("insert", {}, RuntimeError("duplicate"))
        for user in self.users:
            if not hasattr(user, "id") or user.id is None:
                user.id = uuid.uuid4()
                user.is_active = True
                user.created_at = datetime.now(UTC)

    async def commit(self) -> None:
        return None

    async def refresh(self, _value) -> None:  # type: ignore[no-untyped-def]
        return None

    async def rollback(self) -> None:
        return None


def _client(
    session: FakeAdminSession, roles: tuple[str, ...] = ("propietario",)
) -> TestClient:
    app = FastAPI()
    app.include_router(admin_api.router, prefix="/api")
    register_exception_handlers(app)
    app.state.audit_recorder = None
    principal = Principal(
        sub=str(uuid.uuid4()),
        tenant_id=session.tenant_id,
        roles=roles,
        email="dueno@demo-ficticia.invalid",
    )
    app.dependency_overrides[get_current_principal] = lambda: principal
    app.dependency_overrides[tenant_session] = lambda: session
    return TestClient(app)


def test_owner_reads_and_updates_only_allowed_tenant_profile_fields() -> None:
    session = FakeAdminSession()
    client = _client(session)

    before = client.get("/api/admin/perfil")
    assert before.status_code == 200
    assert before.json() == {
        "id": str(session.tenant_id),
        "nombre": "Clínica Ficticia",
        "slug_reserva": "demo-ficticia",
        "moneda": "ARS",
    }

    updated = client.patch(
        "/api/admin/perfil",
        json={
            "nombre": "Consultorio Demo",
            "moneda": "ARS",
            "slug_reserva": "otro-tenant",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["nombre"] == "Consultorio Demo"
    assert session.tenant.slug_reserva == "demo-ficticia"
    wrong_currency = client.patch(
        "/api/admin/perfil", json={"nombre": "Consultorio Demo", "moneda": "USD"}
    )
    assert wrong_currency.status_code == 422


def test_create_user_hashes_password_and_never_returns_secret() -> None:
    session = FakeAdminSession()
    client = _client(session)
    password = "Ficticia-Local-2030!"

    response = client.post(
        "/api/admin/usuarios",
        json={
            "email": " NUEVO@DEMO-FICTICIA.INVALID ",
            "nombre": "Usuario Ficticio",
            "password_inicial": password,
            "rol": "recepcion",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["email"] == "nuevo@demo-ficticia.invalid"
    assert "password" not in response.json() and "password_hash" not in response.json()
    assert session.users[0].tenant_id == session.tenant_id
    assert session.users[0].password_hash != password
    assert verify_password(session.users[0].password_hash, password)
    assert len(session.user_roles) == 1


def test_user_listing_is_scoped_to_principal_tenant() -> None:
    session = FakeAdminSession()
    session.rows = [
        (
            SimpleNamespace(
                id=uuid.uuid4(),
                tenant_id=session.tenant_id,
                email="staff@demo-ficticia.invalid",
                nombre="Staff Ficticio",
                is_active=True,
                created_at=datetime.now(UTC),
            ),
            "recepcion",
        )
    ]
    response = _client(session).get("/api/admin/usuarios")
    assert response.status_code == 200
    assert response.json()[0]["email"] == "staff@demo-ficticia.invalid"
    sql = str(session.last_statement)
    assert "usuario.tenant_id" in sql
    assert "user_rol.tenant_id" in sql


def test_non_owner_is_forbidden_and_invalid_role_or_password_is_rejected() -> None:
    session = FakeAdminSession()
    client = _client(session, ("recepcion",))
    denied = client.get("/api/admin/perfil")
    assert denied.status_code == 403
    assert session.scalar_calls == 0

    owner = _client(session)
    bad_role = owner.post(
        "/api/admin/usuarios",
        json={
            "email": "staff@demo-ficticia.invalid",
            "nombre": "Staff Demo",
            "password_inicial": "Ficticia-Local-2030!",
            "rol": "propietario",
        },
    )
    weak_password = owner.post(
        "/api/admin/usuarios",
        json={
            "email": "staff@demo-ficticia.invalid",
            "nombre": "Staff Demo",
            "password_inicial": "corta",
            "rol": "recepcion",
        },
    )
    assert bad_role.status_code == 422
    assert weak_password.status_code == 422


def test_duplicate_user_email_is_a_conflict() -> None:
    session = FakeAdminSession()
    session.duplicate = True
    response = _client(session).post(
        "/api/admin/usuarios",
        json={
            "email": "staff@demo-ficticia.invalid",
            "nombre": "Staff Demo",
            "password_inicial": "Ficticia-Local-2030!",
            "rol": "recepcion",
        },
    )
    assert response.status_code == 409


def test_audit_event_persists_resource_id(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    session = SimpleNamespace(events=[], execute=_async_noop)
    session.add = lambda event: session.events.append(event)
    session.begin = lambda: _AsyncContext(session)

    class FakeFactory:
        def __call__(self):  # type: ignore[no-untyped-def]
            return _AsyncContext(session)

    monkeypatch.setattr(audit_api, "get_session_factory", lambda: FakeFactory())
    resource_id = str(uuid.uuid4())
    asyncio.run(
        audit_api.record_tenant_event(
            tenant_id=uuid.uuid4(),
            actor_usuario_id=None,
            evento="recurso_consultado",
            recurso="administracion",
            recurso_id=resource_id,
            metodo="GET",
            ruta="/api/admin/recurso",
        )
    )
    assert session.events[0].recurso_id == resource_id


async def _async_noop(*_args, **_kwargs):  # type: ignore[no-untyped-def]
    return None
