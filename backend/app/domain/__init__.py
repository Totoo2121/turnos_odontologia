"""C-02 domain package: core multi-tenant entities and lifecycle mixin."""

# C-13: register odontograma/adjuntos/consentimientos on the shared metadata.
from app.domain.clinica import models as _clinica_models  # noqa: F401,E402
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

# C-17: register audit/export tables after Base is initialized.
from app.domain.admin import models as _admin_models  # noqa: F401,E402
from app.domain.etapa2 import models as _etapa2_models  # noqa: F401,E402

# C-11: register notification models on the shared metadata (Alembic sees them).
from app.domain.notificaciones import (
    models as _notificaciones_models,  # noqa: F401,E402
)

# C-12: register pacientes + HCE models on the shared metadata.
from app.domain.pacientes import models as _pacientes_models  # noqa: F401,E402

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
