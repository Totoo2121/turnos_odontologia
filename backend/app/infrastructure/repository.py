"""Tenant-scoped data access (C-02, D8): BaseRepository[T] + UnitOfWork.

Defense in depth: the repository ALWAYS filters by ``tenant_id`` (fail-closed
— a missing/invalid tenant or an unscoped model raises instead of leaking),
and ``UnitOfWork`` pins ``app.tenant_id`` transaction-locally so the DB RLS
policies from Migración 001 enforce the same boundary underneath.
"""

import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar, cast

from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Base

T = TypeVar("T", bound=Base)

# Transaction-LOCAL GUC pin (dies with the txn; pool-safe). Strict on purpose:
# without it the RLS policies fail closed instead of leaking cross-tenant.
SET_TENANT_GUC_SQL = "SELECT set_config('app.tenant_id', :tenant_id, true)"


class TenantScopeError(ValueError):
    """Raised whenever tenant scoping cannot be guaranteed (fail-closed)."""


def coerce_tenant_id(value: uuid.UUID | str | None) -> uuid.UUID:
    """Validate a tenant id up front; None/malformed never yields a scope."""
    if value is None:
        raise TenantScopeError("tenant_id is required (refusing unscoped access)")
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise TenantScopeError(f"malformed tenant_id: {value!r}") from exc


class BaseRepository(Generic[T]):
    """Generic async CRUD that only ever touches rows of one tenant.

    ``model`` must expose a ``tenant_id`` column (``Rol`` is refused: the
    global catalog is read directly, never through a tenant scope).
    ``session`` may be None for pure query compilation; data access requires
    a live session.
    """

    def __init__(
        self,
        session: AsyncSession | None,
        model: type[T],
        tenant_id: uuid.UUID | str | None,
    ) -> None:
        if "tenant_id" not in model.__table__.columns:
            raise TenantScopeError(
                f"{model.__tablename__} has no tenant_id: refusing unscoped "
                "repository (global catalogs bypass tenant scoping by design)"
            )
        self._session = session
        self._model = model
        self._tenant_id = coerce_tenant_id(tenant_id)

    @property
    def tenant_id(self) -> uuid.UUID:
        """The tenant this repository instance is pinned to."""
        return self._tenant_id

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise TenantScopeError("repository has no session (query-only instance)")
        return self._session

    def query(self, *, include_deleted: bool = False) -> Select[Any]:
        """Scoped SELECT: tenant filter always; soft-deleted hidden by default."""
        tenant_column: Any = getattr(self._model, "tenant_id")
        stmt = select(self._model).where(tenant_column == self._tenant_id)
        columns = self._model.__table__.columns
        if not include_deleted and "deleted_at" in columns:
            stmt = stmt.where(getattr(self._model, "deleted_at").is_(None))
        return stmt.order_by(getattr(self._model, "created_at"))

    async def get(
        self, entity_id: uuid.UUID, *, include_deleted: bool = False
    ) -> T | None:
        """Fetch one row by id within this tenant (cross-tenant → None)."""
        stmt = self.query(include_deleted=include_deleted).where(
            self._model.__table__.c.id == entity_id
        )
        result = await self._require_session().execute(stmt)
        return cast("T | None", result.scalar_one_or_none())

    async def list(
        self,
        *,
        include_deleted: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[T]:
        """List rows of this tenant only (soft-deleted hidden by default)."""
        stmt = self.query(include_deleted=include_deleted).limit(limit).offset(offset)
        result = await self._require_session().execute(stmt)
        return cast("Sequence[T]", result.scalars().all())

    async def add(self, obj: T) -> T:
        """Persist a new row, stamping our tenant (foreign tenant → refused)."""
        obj_tenant = getattr(obj, "tenant_id", None)
        if obj_tenant is None:
            setattr(obj, "tenant_id", self._tenant_id)
        elif obj_tenant != self._tenant_id:
            raise TenantScopeError(
                "object tenant does not match repository tenant (refusing)"
            )
        session = self._require_session()
        session.add(obj)
        await session.flush()
        return obj

    async def soft_delete(self, entity_id: uuid.UUID) -> bool:
        """Logical delete (deleted_at + is_active=false); never physical."""
        if "deleted_at" not in self._model.__table__.columns:
            raise ValueError(
                f"{self._model.__tablename__} has no deleted_at: physical "
                "DELETE only (link tables carry no lifecycle)"
            )
        row = await self.get(entity_id, include_deleted=True)
        if row is None:
            return False
        setattr(row, "deleted_at", datetime.now(UTC))
        if "is_active" in self._model.__table__.columns:
            setattr(row, "is_active", False)
        await self._require_session().flush()
        return True


class UnitOfWork:
    """Short-lived tenant transaction: pins GUC, commits all-or-nothing."""

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession] | None,
        tenant_id: uuid.UUID | str | None,
    ) -> None:
        self._tenant_id = coerce_tenant_id(tenant_id)
        if session_factory is None:
            raise TenantScopeError("UnitOfWork requires a session factory")
        self._factory: Callable[[], AsyncSession] = session_factory
        self._session: AsyncSession | None = None

    @property
    def session(self) -> AsyncSession:
        """The live session (only valid inside the context manager)."""
        if self._session is None:
            raise TenantScopeError("UnitOfWork is not open (use 'async with')")
        return self._session

    def repo(self, model: type[T]) -> BaseRepository[T]:
        """Repository for ``model`` pinned to this transaction's tenant."""
        return BaseRepository(self.session, model, self._tenant_id)

    async def __aenter__(self) -> "UnitOfWork":
        """Open a session and pin the tenant GUC transaction-locally."""
        self._session = self._factory()
        await self._session.execute(
            text(SET_TENANT_GUC_SQL), {"tenant_id": str(self._tenant_id)}
        )
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        """Commit on success, roll everything back on any failure."""
        assert self._session is not None
        try:
            if exc_type is None:
                await self._session.commit()
            else:
                await self._session.rollback()
        finally:
            await self._session.close()
            self._session = None
        return False

    async def rollback(self) -> None:
        """Explicit rollback escape hatch (tests, compensations)."""
        await self.session.rollback()


def tenant_row_count_stmt(model: type[T], tenant_id: uuid.UUID) -> Select[Any]:
    """Count rows of one tenant (admin/diagnostics seam, still scoped)."""
    tenant_column: Any = getattr(model, "tenant_id")
    return select(func.count()).select_from(model).where(tenant_column == tenant_id)
