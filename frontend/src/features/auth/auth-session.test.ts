/** RED — task 2.3: logout best-effort + hydrate inicial. Datos 100% ficticios. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AUTH_STORAGE_KEY } from "../../shared/storage";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("auth-store logout/hydrate (RED 2.3)", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    vi.resetModules();
  });

  it("logout llama al backend pero limpia siempre aunque el remoto falle", async () => {
    const fetchImpl = vi.fn(async (_input: string | URL | Request) =>
      jsonResponse(500, { detail: "caído" }),
    );
    vi.stubGlobal("fetch", fetchImpl);

    const { useAuthStore } = await import("./auth-store");
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({ accessToken: "access-ficticio-3" }));
    useAuthStore.setState({
      accessToken: "access-ficticio-3",
      user: {
        id: "u-ficticia-3",
        email: "recepcion@ficticio.test",
        roles: ["recepcion"],
        tenantId: "t-ficticio-1",
      },
      status: "authenticated",
      error: null,
    });

    await useAuthStore.getState().logout();

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(String(fetchImpl.mock.calls[0]?.[0])).toMatch(/\/api\/auth\/logout$/);
    const state = useAuthStore.getState();
    expect(state.accessToken).toBeNull();
    expect(state.user).toBeNull();
    expect(state.status).toBe("unauthenticated");
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBeNull();
  });

  it("TRIANGULATE: logout limpia aunque fetch lance (red caída)", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("network down");
    });
    vi.stubGlobal("fetch", fetchImpl);

    const { useAuthStore } = await import("./auth-store");
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({ accessToken: "access-ficticio-4" }));
    useAuthStore.setState({
      accessToken: "access-ficticio-4",
      user: null,
      status: "authenticated",
      error: null,
    });

    await useAuthStore.getState().logout();

    expect(useAuthStore.getState().status).toBe("unauthenticated");
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBeNull();
  });

  it("hydrate con /me válido restaura sesión autenticada", async () => {
    const fetchImpl = vi.fn(async (input: string | URL | Request) => {
      expect(String(input)).toMatch(/\/api\/auth\/me$/);
      return jsonResponse(200, {
        id: "u-ficticia-5",
        email: "odonto@ficticio.test",
        roles: ["odontologo"],
        tenantId: "t-ficticio-1",
      });
    });
    vi.stubGlobal("fetch", fetchImpl);

    const { useAuthStore } = await import("./auth-store");
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({ accessToken: "access-ficticio-5" }));
    useAuthStore.setState({
      accessToken: "access-ficticio-5",
      user: null,
      status: "idle",
      error: null,
    });

    await useAuthStore.getState().hydrate();

    const state = useAuthStore.getState();
    expect(state.status).toBe("authenticated");
    expect(state.user).toMatchObject({ email: "odonto@ficticio.test", roles: ["odontologo"] });
  });

  it("TRIANGULATE: hydrate con 401 deja sesión limpia sin reintentar", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(401, { detail: "expired" }));
    vi.stubGlobal("fetch", fetchImpl);

    const { useAuthStore } = await import("./auth-store");
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({ accessToken: "access-vencido" }));
    useAuthStore.setState({
      accessToken: "access-vencido",
      user: null,
      status: "idle",
      error: null,
    });

    await useAuthStore.getState().hydrate();

    const state = useAuthStore.getState();
    expect(state.status).toBe("unauthenticated");
    expect(state.accessToken).toBeNull();
    expect(state.user).toBeNull();
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBeNull();
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});
