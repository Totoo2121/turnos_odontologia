/** RED — task 2.2: post() espeja request() (401→refresh→retry único).
 * Datos 100% ficticios.
 */
import { describe, expect, it, vi } from "vitest";
import { ApiClient } from "./api-client";
import { AUTH_STORAGE_KEY, type TokenStore } from "./storage";

function memoryStore(seed: Record<string, string> = {}): TokenStore {
  const data = new Map<string, string>(Object.entries(seed));
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => {
      data.set(key, value);
    },
    removeItem: (key) => {
      data.delete(key);
    },
  };
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("ApiClient.post (RED 2.2)", () => {
  it("reintenta exactamente una vez con token renovado tras 401 en POST", async () => {
    const store = memoryStore({
      [AUTH_STORAGE_KEY]: JSON.stringify({ accessToken: "stale-access" }),
    });
    const seenBodies: Array<string | null> = [];
    const fetchImpl = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/auth/refresh")) {
        expect(init?.credentials).toBe("include");
        return jsonResponse(200, { accessToken: "fresh-access" });
      }
      const auth = new Headers(init?.headers).get("authorization");
      seenBodies.push(
        typeof init?.body === "string" ? init.body : init?.body == null ? null : "non-string",
      );
      if (auth === "Bearer stale-access") {
        return jsonResponse(401, { detail: "expired" });
      }
      return jsonResponse(200, { created: true });
    });

    const client = new ApiClient({ baseUrl: "http://api.test", store, fetchImpl });
    const data = await client.post<{ created: boolean }>("/api/turnos", {
      pacienteId: "p-ficticio-1",
    });

    expect(data).toEqual({ created: true });
    expect(fetchImpl).toHaveBeenCalledTimes(3);
    expect(seenBodies).toEqual([
      JSON.stringify({ pacienteId: "p-ficticio-1" }),
      JSON.stringify({ pacienteId: "p-ficticio-1" }),
    ]);
    const retryInit = fetchImpl.mock.calls[2]?.[1] as RequestInit | undefined;
    expect(new Headers(retryInit?.headers).get("authorization")).toBe("Bearer fresh-access");
    expect(retryInit?.method).toBe("POST");
  });

  it("TRIANGULATE: refresh rechazado en POST limpia el store sin reintento extra", async () => {
    const store = memoryStore({
      [AUTH_STORAGE_KEY]: JSON.stringify({ accessToken: "stale-access" }),
    });
    const fetchImpl = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/api/auth/refresh")) {
        return jsonResponse(401, { detail: "bad refresh" });
      }
      return jsonResponse(401, { detail: "expired" });
    });

    const client = new ApiClient({ baseUrl: "http://api.test", store, fetchImpl });

    await expect(
      client.post("/api/turnos", { pacienteId: "p-ficticio-9" }),
    ).rejects.toThrow();
    expect(store.getItem(AUTH_STORAGE_KEY)).toBeNull();
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });
});
