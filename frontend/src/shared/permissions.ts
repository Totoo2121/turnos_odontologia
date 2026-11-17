/**
 * C-15 role predicates mirrored from the backend RBAC matrix (KB 03).
 * The server is the source of truth: hiding a control here is UX, not security.
 */
import type { Role } from "../features/auth/auth-store";

function hasAny(roles: Role[], allowed: readonly Role[]): boolean {
  return roles.some((role) => allowed.includes(role));
}

const CLINICAL_ROLES: readonly Role[] = ["propietario", "odontologo"];
const AGENDA_WRITE_ROLES: readonly Role[] = [
  "propietario",
  "odontologo",
  "recepcion",
];
const AGENDA_CREATE_ROLES: readonly Role[] = ["propietario", "recepcion"];
const CASH_WRITE_ROLES: readonly Role[] = ["propietario", "recepcion"];

/** Clinical tabs and HCE reads: owner/treating professionals only. */
export function canAccessClinical(roles: Role[]): boolean {
  return hasAny(roles, CLINICAL_ROLES);
}

/** Evolutions, odontogram events, budgets and consents. */
export function canWriteClinical(roles: Role[]): boolean {
  return hasAny(roles, CLINICAL_ROLES);
}

/** Closing a turn as attended (agenda U). */
export function canWriteAgenda(roles: Role[]): boolean {
  return hasAny(roles, AGENDA_WRITE_ROLES);
}

/** Creating the follow-up appointment (agenda C). */
export function canCreateAgenda(roles: Role[]): boolean {
  return hasAny(roles, AGENDA_CREATE_ROLES);
}

/** Registering a payment (cobros C); odontólogo keeps read-only access. */
export function canCharge(roles: Role[]): boolean {
  return hasAny(roles, CASH_WRITE_ROLES);
}
