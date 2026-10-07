"""C-03 RBAC matrix (KB 03 + RN-SE-02/03, D10).

Pure role×resource behavior: no DB, no HTTP. Actions are C/R/U/D plus X
(execute: audit export, patient self-payment). Anything not explicitly
allowed is denied (fail-closed). Ownership scoping ("sus turnos", "propios")
is enforced at the query layer by consumers; the HCE treating/derivation
half of RN-SE-02 opens in C-12 — until then non-owner access denies unless
the caller proves owner/treating/derived status via `may_access_hce`.
"""

from __future__ import annotations

from app.shared.exceptions import AppError

Role = str
Resource = str
Action = str

RESOURCES: tuple[str, ...] = (
    "agenda",
    "pacientes",
    "odontograma",
    "cobros",
    "reportes",
    "config",
    "auditoria",
)

# KB 03 permission matrix: (role, resource) -> allowed actions.
MATRIX: dict[tuple[Role, Resource], frozenset[Action]] = {
    ("propietario", "agenda"): frozenset({"C", "R", "U", "D"}),
    ("propietario", "pacientes"): frozenset({"C", "R", "U", "D"}),
    ("propietario", "odontograma"): frozenset({"R"}),
    ("propietario", "cobros"): frozenset({"C", "R", "U", "D"}),
    ("propietario", "reportes"): frozenset({"R"}),
    ("propietario", "config"): frozenset({"C", "R", "U", "D"}),
    ("propietario", "auditoria"): frozenset({"R", "X"}),
    ("odontologo", "agenda"): frozenset({"R", "U", "D"}),
    ("odontologo", "pacientes"): frozenset({"C", "R", "U", "D"}),
    ("odontologo", "odontograma"): frozenset({"C", "R", "U", "D"}),
    ("odontologo", "cobros"): frozenset({"R"}),
    ("odontologo", "reportes"): frozenset({"R"}),
    ("recepcion", "agenda"): frozenset({"C", "R", "U", "D"}),
    ("recepcion", "pacientes"): frozenset({"C", "R"}),
    ("recepcion", "odontograma"): frozenset({"R"}),
    ("recepcion", "cobros"): frozenset({"C", "R", "U", "D"}),
    ("recepcion", "reportes"): frozenset({"R"}),
    ("asistente", "agenda"): frozenset({"R"}),
    ("asistente", "pacientes"): frozenset({"C", "R"}),
    ("asistente", "odontograma"): frozenset({"R"}),
    ("paciente-portal", "agenda"): frozenset({"C", "R"}),
    ("paciente-portal", "pacientes"): frozenset({"R"}),
    ("paciente-portal", "odontograma"): frozenset({"R"}),
    ("paciente-portal", "cobros"): frozenset({"X"}),
}

# Roles allowed to write clinical evolutions (RN-SE-03): reception and
# assistants never modify them, even where the matrix grants ficha reads.
_EVOLUTION_WRITERS: frozenset[Role] = frozenset({"propietario", "odontologo"})


def allowed_actions(role: Role, resource: Resource) -> frozenset[Action]:
    """Actions granted to a role on a resource (empty when unknown)."""
    return MATRIX.get((role, resource), frozenset())


def can(role: Role, resource: Resource, action: Action) -> bool:
    """Check one role×resource×action triple (fail-closed on unknowns)."""
    return action in allowed_actions(role, resource)


def can_any(
    roles: tuple[Role, ...] | list[Role], resource: Resource, action: Action
) -> bool:
    """Check whether ANY of the principal's roles grants the action."""
    return any(can(role, resource, action) for role in roles)


def authorize(
    roles: tuple[Role, ...] | list[Role], resource: Resource, action: Action
) -> None:
    """Enforce the matrix, raising uniform 403 on denial (no partial 200)."""
    if not can_any(roles, resource, action):
        raise AppError("forbidden", 403)


def may_modify_evolution(roles: tuple[Role, ...] | list[Role]) -> bool:
    """RN-SE-03: only clinical roles write evolutions (reception never)."""
    return any(role in _EVOLUTION_WRITERS for role in roles)


def may_access_hce(
    roles: tuple[Role, ...] | list[Role], *, is_owner_treating_or_derived: bool
) -> bool:
    """RN-SE-02: HCE visible to owner/propietario/treating/derivation only.

    Until C-12 provides the treating/derivation tables, callers pass False
    for non-owners and the guard denies fail-closed (documented in D10).
    """
    if "propietario" in roles:
        return True
    return bool(is_owner_treating_or_derived)
