"""C-03 RBAC matrix tests (task 5.2) — RED first.

Pure behavior tests over `application/rbac.py`: the KB 03 role×resource
matrix, RN-SE-02 fail-closed HCE visibility (until C-12), RN-SE-03 clinical
evolution protection, and fail-closed defaults. No DB needed.
"""

from __future__ import annotations

import pytest


def test_propietario_full_matrix() -> None:
    """WHEN propietario checked THEN CRUD agenda/pacientes/cobros/config, R+ver."""
    from app.application.rbac import can

    for resource in ("agenda", "pacientes", "cobros", "config"):
        for action in ("C", "R", "U", "D"):
            assert can("propietario", resource, action) is True
    assert can("propietario", "odontograma", "R") is True
    assert can("propietario", "odontograma", "U") is False
    assert can("propietario", "reportes", "R") is True
    assert can("propietario", "auditoria", "R") is True
    assert can("propietario", "auditoria", "X") is True


def test_odontologo_own_scope_actions() -> None:
    """WHEN odontologo checked THEN RUD agenda, CRUD clinica, R cobros/reportes."""
    from app.application.rbac import can

    assert can("odontologo", "agenda", "R") is True
    assert can("odontologo", "agenda", "D") is True
    assert can("odontologo", "agenda", "C") is False
    assert can("odontologo", "pacientes", "C") is True
    assert can("odontologo", "odontograma", "U") is True
    assert can("odontologo", "cobros", "R") is True
    assert can("odontologo", "cobros", "C") is False
    assert can("odontologo", "reportes", "R") is True
    assert can("odontologo", "config", "R") is False
    assert can("odontologo", "auditoria", "X") is False


def test_recepcion_no_clinical_evolutions() -> None:
    """WHEN recepcion checked THEN CRUD turnos/cobros but 403 on evolutions."""
    from app.application.rbac import can, may_modify_evolution

    assert can("recepcion", "agenda", "C") is True
    assert can("recepcion", "pacientes", "C") is True
    assert can("recepcion", "pacientes", "D") is False
    assert can("recepcion", "odontograma", "R") is True
    assert can("recepcion", "cobros", "C") is True
    assert may_modify_evolution(("recepcion",)) is False
    assert may_modify_evolution(("odontologo",)) is True
    assert may_modify_evolution(("propietario",)) is True


def test_asistente_read_only_support() -> None:
    """WHEN asistente checked THEN R turnos/ficha/odontograma, nothing else."""
    from app.application.rbac import can, may_modify_evolution

    assert can("asistente", "agenda", "R") is True
    assert can("asistente", "agenda", "C") is False
    assert can("asistente", "pacientes", "C") is True
    assert can("asistente", "pacientes", "D") is False
    assert can("asistente", "odontograma", "R") is True
    assert can("asistente", "cobros", "R") is False
    assert can("asistente", "reportes", "R") is False
    assert may_modify_evolution(("asistente",)) is False


def test_paciente_portal_own_only() -> None:
    """WHEN paciente-portal checked THEN own CR/R + pay own, nothing else."""
    from app.application.rbac import can

    assert can("paciente-portal", "agenda", "C") is True
    assert can("paciente-portal", "agenda", "D") is False
    assert can("paciente-portal", "pacientes", "R") is True
    assert can("paciente-portal", "pacientes", "U") is False
    assert can("paciente-portal", "odontograma", "R") is True
    assert can("paciente-portal", "cobros", "X") is True
    assert can("paciente-portal", "cobros", "C") is False
    assert can("paciente-portal", "reportes", "R") is False
    assert can("paciente-portal", "config", "R") is False


def test_unknown_role_or_resource_denied_fail_closed() -> None:
    """WHEN role/resource unknown THEN deny (fail-closed, never 200 partial)."""
    from app.application.rbac import can

    assert can("superusuario-ficticio", "agenda", "R") is False
    assert can("recepcion", "receta-ficticia", "R") is False
    assert can("recepcion", "agenda", "X") is False


def test_hce_foreign_denied_without_derivation() -> None:
    """WHEN odontologo eyes foreign HCE w/o derivation THEN deny (RN-SE-02)."""
    from app.application.rbac import may_access_hce

    assert may_access_hce(("odontologo",), is_owner_treating_or_derived=False) is False
    assert may_access_hce(("odontologo",), is_owner_treating_or_derived=True) is True
    assert may_access_hce(("propietario",), is_owner_treating_or_derived=False) is True
    assert may_access_hce(("recepcion",), is_owner_treating_or_derived=True) is True


def test_authorize_raises_uniform_403() -> None:
    """WHEN authorize denied THEN AppError 403 with no side effects."""
    from app.application.rbac import authorize
    from app.shared.exceptions import AppError

    with pytest.raises(AppError) as exc_info:
        authorize(("asistente",), "cobros", "C")
    assert exc_info.value.status_code == 403
    authorize(("recepcion",), "cobros", "C")  # allowed: must not raise
