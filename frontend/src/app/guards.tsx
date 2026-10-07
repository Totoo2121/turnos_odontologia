import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuthStore, type Role } from "../features/auth/auth-store";

export type RouteKey = "agenda" | "pacientes" | "caja" | "reportes" | "admin";

/**
 * Única fuente rol→rutas (spec §guards, matriz KB 03).
 * La usan los guards Y la navegación del shell: no pueden divergir.
 */
export const ROLE_ROUTES: Record<RouteKey, Role[]> = {
  agenda: ["propietario", "odontologo", "recepcion", "asistente"],
  pacientes: ["propietario", "odontologo", "recepcion", "asistente"],
  caja: ["propietario", "recepcion", "odontologo"],
  reportes: ["propietario", "recepcion", "odontologo"],
  admin: ["propietario"],
};

export const ROUTE_PATHS: Record<RouteKey, string> = {
  agenda: "/agenda",
  pacientes: "/pacientes",
  caja: "/caja",
  reportes: "/reportes",
  admin: "/admin",
};

const ROUTE_LABELS: Record<RouteKey, string> = {
  agenda: "Agenda",
  pacientes: "Pacientes",
  caja: "Caja",
  reportes: "Reportes",
  admin: "Admin",
};

const NAV_ORDER: RouteKey[] = ["agenda", "pacientes", "caja", "reportes", "admin"];

export interface NavRoute {
  key: RouteKey;
  path: string;
  label: string;
}

/** Rutas visibles para un conjunto de roles (nav del shell). */
export function routesForRoles(roles: Role[]): NavRoute[] {
  return NAV_ORDER.filter((key) => ROLE_ROUTES[key].some((role) => roles.includes(role))).map(
    (key) => ({ key, path: ROUTE_PATHS[key], label: ROUTE_LABELS[key] }),
  );
}

/** Exige sesión válida; sin sesión redirige a /login recordando el origen. */
export function RequireAuth({ children }: { children: ReactNode }): JSX.Element {
  const status = useAuthStore((s) => s.status);
  const location = useLocation();
  if (status === "authenticated") {
    return <>{children}</>;
  }
  if (status === "idle" || status === "loading") {
    return <p>Cargando sesión…</p>;
  }
  return <Navigate to="/login" state={{ from: location.pathname }} replace />;
}

/** Exige al menos uno de los roles permitidos; sin permiso va a /403. */
export function RequireRole({
  allowed,
  children,
}: {
  allowed: Role[];
  children: ReactNode;
}): JSX.Element {
  const roles = useAuthStore((s) => s.user?.roles);
  const granted = roles?.some((role) => allowed.includes(role)) ?? false;
  if (!granted) {
    return <Navigate to="/403" replace />;
  }
  return <>{children}</>;
}
