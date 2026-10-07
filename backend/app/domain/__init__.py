"""C-02 domain package: core multi-tenant entities and lifecycle mixin."""

from app.domain.mixins import AuditMixin
from app.domain.models import (
    PASSWORD_UNSET_MARKER,
    ROLE_NAMES,
    SLUG_PATTERN,
    SLUG_RE,
    Base,
    Rol,
    Sucursal,
    Tenant,
    UserRol,
    Usuario,
)

__all__ = [
    "AuditMixin",
    "Base",
    "PASSWORD_UNSET_MARKER",
    "ROLE_NAMES",
    "Rol",
    "SLUG_PATTERN",
    "SLUG_RE",
    "Sucursal",
    "Tenant",
    "UserRol",
    "Usuario",
]
