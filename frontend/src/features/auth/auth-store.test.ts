/** RED — task 2.1: login válido guarda access + hidrata user/roles; 401 no guarda sesión.
 * Datos 100% ficticios (dominio ficticio.test).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AUTH_STORAGE_KEY } from "../../shared/storage";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("auth-store login (RED 2.1)", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    vi.resetModules();
  });

  it("login válido guarda access e hidrata user/roles vía /me", async () => {
    const fetchImpl = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/api/auth/login")) {
        return jsonResponse(200, { accessToken: "access-ficticio-1" });
      }
      if (url.endsWith("/api/auth/me")) {
        return jsonResponse(200, {
          id: "u-ficticia-1",
          email: "recepcion@ficticio.test",
          roles: ["recepcion"],
          tenantId: "t-ficticio-1",
        });
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchImpl);

    const { useAuthStore } = await import("./auth-store");
    useAuthStore.setState({
      accessToken: null,
      user: null,
      status: "idle",
      error: null,
    });

    const result = await useAuthStore.getState().login("recepcion@ficticio.test", "Secreta123");

    expect(result.ok).toBe(true);
    const state = useAuthStore.getState();
    expect(state.accessToken).toBe("access-ficticio-1");
    expect(state.user).toMatchObject({
      email: "recepcion@ficticio.test",
      roles: ["recepcion"],
    });
    expect(state.status).toBe("authenticated");
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toContain("access-ficticio-1");
  });

  it("credencial inválida (401) muestra error genérico y no guarda sesión", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(401, { detail: "bad" }));
    vi.stubGlobal("fetch", fetchImpl);

    const { useAuthStore } = await import("./auth-store");
    useAuthStore.setState({
      accessToken: null,
      user: null,
      status: "idle",
      error: null,
    });

    const result = await useAuthStore.getState().login("nadie@ficticio.test", "Wrong123");

    expect(result.ok).toBe(false);
    if (result.ok) {
      throw new Error("se esperaba un login fallido (ficticio)");
    }
    // Error genérico: no distingue email de password.
    expect(result.error).toBe("Credenciales inválidas. Verificá e intentá de nuevo.");
    expect(String(result.error)).not.toMatch(/email/i);
    expect(String(result.error)).not.toMatch(/password|contrase/i);
    const state = useAuthStore.getState();
    expect(state.accessToken).toBeNull();
    expect(state.user).toBeNull();
    expect(state.status).toBe("unauthenticated");
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBeNull();
  });

  it("TRIANGULATE: normaliza email con mayúsculas y espacios antes de enviarlo", async () => {
    let sentBody: unknown = null;
    const fetchImpl = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/auth/login")) {
        sentBody = JSON.parse(String(init?.body));
        return jsonResponse(200, { accessToken: "access-ficticio-2" });
      }
      if (url.endsWith("/api/auth/me")) {
        return jsonResponse(200, {
          id: "u-ficticia-2",
          email: "recepcion@ficticio.test",
          roles: ["recepcion"],
          tenantId: "t-ficticio-1",
        });
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchImpl);

    const { useAuthStore } = await import("./auth-store");
    useAuthStore.setState({
      accessToken: null,
      user: null,
      status: "idle",
      error: null,
    });

    const result = await useAuthStore
      .getState()
      .login("  RECEPCION@Ficticio.TEST  ", "Secreta123");

    expect(result.ok).toBe(true);
    expect(sentBody).toEqual({
      email: "recepcion@ficticio.test",
      password: "Secreta123",
    });
    expect(useAuthStore.getState().status).toBe("authenticated");
  });

  it("TRIANGULATE: falla de red muestra el mismo error genérico sin sesión", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("network down");
    });
    vi.stubGlobal("fetch", fetchImpl);

    const { useAuthStore } = await import("./auth-store");
    useAuthStore.setState({
      accessToken: null,
      user: null,
      status: "idle",
      error: null,
    });

    const result = await useAuthStore.getState().login("alguien@ficticio.test", "Secreta123");

    expect(result).toEqual({
      ok: false,
      error: "Credenciales inválidas. Verificá e intentá de nuevo.",
    });
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBeNull();
  });
});
