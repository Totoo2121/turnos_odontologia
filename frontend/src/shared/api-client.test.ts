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

describe("ApiClient", () => {
  it("returns data without refresh when the first request succeeds", async () => {
    const store = memoryStore({
      [AUTH_STORAGE_KEY]: JSON.stringify({ accessToken: "access-a" }),
    });
    const fetchImpl = vi.fn(async () => jsonResponse(200, { status: "ok" }));

    const client = new ApiClient({
      baseUrl: "http://api.test",
      store,
      fetchImpl,
    });
    const data = await client.get<{ status: string }>("/api/health");

    expect(data).toEqual({ status: "ok" });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("retries exactly once with the refreshed token after a 401", async () => {
    const store = memoryStore({
      [AUTH_STORAGE_KEY]: JSON.stringify({ accessToken: "stale-access" }),
    });
    const fetchImpl = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/auth/refresh")) {
        // Cookie refresh: no body, credentials included, no Authorization.
        expect(init?.body).toBeUndefined();
        expect(init?.credentials).toBe("include");
        expect(new Headers(init?.headers).get("authorization")).toBeNull();
        return jsonResponse(200, { accessToken: "fresh-access" });
      }
      const auth = new Headers(init?.headers).get("authorization");
      if (auth === "Bearer stale-access") {
        return jsonResponse(401, { detail: "expired" });
      }
      return jsonResponse(200, { status: "ok" });
    });

    const client = new ApiClient({
      baseUrl: "http://api.test",
      store,
      fetchImpl,
    });
    const data = await client.get<{ status: string }>("/api/health");

    expect(data).toEqual({ status: "ok" });
    // original + refresh + exactly one retry
    expect(fetchImpl).toHaveBeenCalledTimes(3);
    const retryInit = fetchImpl.mock.calls[2]?.[1] as RequestInit | undefined;
    expect(new Headers(retryInit?.headers).get("authorization")).toBe(
      "Bearer fresh-access",
    );
    expect(store.getItem(AUTH_STORAGE_KEY)).toContain("fresh-access");
  });

  it("clears versioned storage and throws when refresh is invalid", async () => {
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

    const client = new ApiClient({
      baseUrl: "http://api.test",
      store,
      fetchImpl,
    });

    await expect(client.get("/api/health")).rejects.toThrow();
    expect(store.getItem(AUTH_STORAGE_KEY)).toBeNull();
    // original + refresh attempt, no further retry
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it("migrates legacy storage carrying a persisted refresh token", async () => {
    const store = memoryStore({
      [AUTH_STORAGE_KEY]: JSON.stringify({
        accessToken: "access-a",
        refreshToken: "legacy-refresh-must-vanish",
      }),
    });
    const fetchImpl = vi.fn(async () => jsonResponse(200, { status: "ok" }));

    const client = new ApiClient({
      baseUrl: "http://api.test",
      store,
      fetchImpl,
    });
    const data = await client.get<{ status: string }>("/api/health");

    expect(data).toEqual({ status: "ok" });
    // Migrated in place: access kept, persisted refresh gone for good.
    expect(store.getItem(AUTH_STORAGE_KEY)).toBe(
      JSON.stringify({ accessToken: "access-a" }),
    );
  });
});
