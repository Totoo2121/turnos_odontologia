import { create } from "zustand";
import { clearTokens, loadTokens, saveTokens } from "../../shared/storage";

/** Roles de la matriz RBAC (KB 03) — única fuente del lado sesión. */
export type Role = "propietario" | "odontologo" | "recepcion" | "asistente";

export interface AuthUser {
  id: string;
  email: string;
  roles: Role[];
  tenantId: string;
}

export type AuthStatus = "idle" | "loading" | "authenticated" | "unauthenticated";

/** Error genérico: nunca distingue email de password (anti-enumeración). */
export const LOGIN_ERROR = "Credenciales inválidas. Verificá e intentá de nuevo.";

/**
 * Ruta por defecto tras el login. Todos los roles tienen `/agenda`
 * (matriz RBAC del spec §guards), que opera como home operativo;
 * el resto de rutas se alcanza por nav. Se recibe `roles` para
 * especializar a futuro sin cambiar a los llamadores.
 */
export function defaultRouteForRoles(_roles: Role[]): string {
  return "/agenda";
}

export type LoginResult = { ok: true } | { ok: false; error: string };

interface AuthState {
  accessToken: string | null;
  user: AuthUser | null;
  status: AuthStatus;
  error: string | null;
  login: (email: string, password: string) => Promise<LoginResult>;
  logout: () => Promise<void>;
  hydrate: () => Promise<void>;
}

const LOGIN_PATH = "/api/auth/login";
const ME_PATH = "/api/auth/me";
const LOGOUT_PATH = "/api/auth/logout";

function resolveApiBase(): string {
  const fromEnv =
    typeof import.meta !== "undefined" &&
    typeof import.meta.env?.VITE_API_BASE_URL === "string" &&
    import.meta.env.VITE_API_BASE_URL.length > 0
      ? import.meta.env.VITE_API_BASE_URL
      : "http://localhost:8000";
  return fromEnv.replace(/\/+$/, "");
}

interface LoginPayload {
  accessToken?: unknown;
  access_token?: unknown;
}

interface MePayload {
  id?: unknown;
  email?: unknown;
  roles?: unknown;
  tenantId?: unknown;
  tenant_id?: unknown;
}

function pickAccess(payload: LoginPayload): string | null {
  const candidate = payload.accessToken ?? payload.access_token;
  return typeof candidate === "string" && candidate.length > 0 ? candidate : null;
}

function parseUser(payload: MePayload): AuthUser | null {
  const { id, email, roles } = payload;
  const tenantId = payload.tenantId ?? payload.tenant_id;
  if (
    typeof id !== "string" ||
    typeof email !== "string" ||
    !Array.isArray(roles) ||
    typeof tenantId !== "string"
  ) {
    return null;
  }
  return { id, email, roles: roles as Role[], tenantId };
}

async function fetchMe(accessToken: string): Promise<AuthUser | null> {
  const response = await fetch(`${resolveApiBase()}${ME_PATH}`, {
    method: "GET",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${accessToken}`,
    },
  });
  if (!response.ok) {
    return null;
  }
  return parseUser((await response.json()) as MePayload);
}

export const useAuthStore = create<AuthState>()((set, get) => ({
  accessToken: loadTokens()?.accessToken ?? null,
  user: null,
  status: "idle",
  error: null,
  login: async (email: string, password: string) => {
    const normalizedEmail = email.trim().toLowerCase();
    set({ status: "loading", error: null });
    let response: Response;
    try {
      response = await fetch(`${resolveApiBase()}${LOGIN_PATH}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email: normalizedEmail, password }),
      });
    } catch {
      clearTokens();
      set({ accessToken: null, user: null, status: "unauthenticated", error: LOGIN_ERROR });
      return { ok: false, error: LOGIN_ERROR };
    }
    if (!response.ok) {
      clearTokens();
      set({ accessToken: null, user: null, status: "unauthenticated", error: LOGIN_ERROR });
      return { ok: false, error: LOGIN_ERROR };
    }
    const accessToken = pickAccess((await response.json()) as LoginPayload);
    if (accessToken === null) {
      clearTokens();
      set({ accessToken: null, user: null, status: "unauthenticated", error: LOGIN_ERROR });
      return { ok: false, error: LOGIN_ERROR };
    }
    saveTokens({ accessToken });
    await get().hydrate();
    if (get().status !== "authenticated") {
      set({ error: LOGIN_ERROR });
      return { ok: false, error: LOGIN_ERROR };
    }
    return { ok: true };
  },
  logout: async () => {
    // Best-effort: se intenta invalidar en el backend, pero la limpieza
    // local ocurre siempre (aunque la red falle).
    try {
      const tokens = loadTokens();
      const headers = new Headers({ "content-type": "application/json" });
      if (tokens !== null) {
        headers.set("authorization", `Bearer ${tokens.accessToken}`);
      }
      await fetch(`${resolveApiBase()}${LOGOUT_PATH}`, {
        method: "POST",
        headers,
        credentials: "include",
      });
    } catch {
      // Intencional: el logout local no depende del remoto.
    } finally {
      clearTokens();
      set({ accessToken: null, user: null, status: "unauthenticated", error: null });
    }
  },
  hydrate: async () => {
    const tokens = loadTokens();
    if (tokens === null) {
      set({ accessToken: null, user: null, status: "unauthenticated", error: null });
      return;
    }
    set({ accessToken: tokens.accessToken, status: "loading", error: null });
    const user = await fetchMe(tokens.accessToken);
    if (user === null) {
      clearTokens();
      set({ accessToken: null, user: null, status: "unauthenticated", error: null });
      return;
    }
    set({ accessToken: tokens.accessToken, user, status: "authenticated", error: null });
  },
}));
