"""C-05 agenda domain package (D1): catalog models live here, not in models.py."""

from app.domain.agenda.models import (  # noqa: F401
    Bloqueo,
    Prestacion,
    Profesional,
    ProfesionalPrestacion,
    Sillon,
)
