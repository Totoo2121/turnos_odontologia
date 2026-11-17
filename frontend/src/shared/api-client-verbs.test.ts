/** C-15: verbos nuevos del api-client (patch/delete/upload/204/detail). Datos ficticios. */
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

function seededStore(): TokenStore {
  return memoryStore({
    [AUTH_STORAGE_KEY]: JSON.stringify({ accessToken: "access-c15" }),
  });
}

describe("ApiClient.patch (C-15)", () => {
  it("envía PATCH con Authorization y body JSON", async () => {
    const fetchImpl = vi.fn(
      async (_input: string | URL | Request, _init?: RequestInit) =>
        jsonResponse(200, { id: "t-1", estado: "confirmado" }),
    );
    const client = new ApiClient({
      baseUrl: "http://api.test",
      store: seededStore(),
      fetchImpl,
    });

    const data = await client.patch<{ estado: string }>("/api/turnos/t-1/estado", {
      estado: "confirmado",
    });

    expect(data.estado).toBe("confirmado");
    const init = fetchImpl.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(init?.method).toBe("PATCH");
    expect(new Headers(init?.headers).get("authorization")).toBe("Bearer access-c15");
    expect(JSON.parse(String(init?.body))).toEqual({ estado: "confirmado" });
  });

  it("reintenta una sola vez con el token renovado tras 401 en PATCH", async () => {
    const store = memoryStore({
      [AUTH_STORAGE_KEY]: JSON.stringify({ accessToken: "stale-access" }),
    });
    const fetchImpl = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      if (String(input).endsWith("/api/auth/refresh")) {
        return jsonResponse(200, { accessToken: "fresh-access" });
      }
      const auth = new Headers(init?.headers).get("authorization");
      return auth === "Bearer stale-access"
        ? jsonResponse(401, { detail: "expired" })
        : jsonResponse(200, { id: "t-1" });
    });
    const client = new ApiClient({ baseUrl: "http://api.test", store, fetchImpl });

    await client.patch("/api/turnos/t-1/estado", { estado: "atendido" });

    expect(fetchImpl).toHaveBeenCalledTimes(3);
    const retry = fetchImpl.mock.calls[2]?.[1] as RequestInit | undefined;
    expect(new Headers(retry?.headers).get("authorization")).toBe("Bearer fresh-access");
  });
});

describe("ApiClient.upload (C-15)", () => {
  it("envía multipart sin content-type manual y con Authorization", async () => {
    const fetchImpl = vi.fn(
      async (_input: string | URL | Request, _init?: RequestInit) =>
        jsonResponse(201, { id: "a-1" }),
    );
    const client = new ApiClient({
      baseUrl: "http://api.test",
      store: seededStore(),
      fetchImpl,
    });
    const form = new FormData();
    form.append("tipo", "rx");
    form.append("archivo", new Blob(["ficticio"]), "rx-ficticia.png");

    await client.upload("/api/historias-clinicas/h-1/adjuntos", form);

    const init = fetchImpl.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(init?.body).toBe(form);
    const headers = new Headers(init?.headers);
    expect(headers.get("content-type")).toBeNull();
    expect(headers.get("authorization")).toBe("Bearer access-c15");
  });
});

describe("ApiClient.delete (C-15)", () => {
  it("tolera 204 sin cuerpo", async () => {
    const fetchImpl = vi.fn(async () => new Response(null, { status: 204 }));
    const client = new ApiClient({
      baseUrl: "http://api.test",
      store: seededStore(),
      fetchImpl,
    });

    await expect(client.delete("/api/presupuestos/p-1")).resolves.toBeUndefined();
  });

  it("envía DELETE autenticado y sin cuerpo", async () => {
    const fetchImpl = vi.fn(
      async (_input: string | URL | Request, _init?: RequestInit) =>
        new Response(null, { status: 204 }),
    );
    const client = new ApiClient({
      baseUrl: "http://api.test",
      store: seededStore(),
      fetchImpl,
    });

    await client.delete("/api/presupuestos/p-ficticio-1");

    const init = fetchImpl.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(init?.method).toBe("DELETE");
    expect(init?.body).toBeUndefined();
    expect(new Headers(init?.headers).get("authorization")).toBe("Bearer access-c15");
  });
});

describe("ApiClient.download (C-15)", () => {
  it("descarga un PDF autenticado como blob", async () => {
    const fetchImpl = vi.fn(
      async (_input: string | URL | Request, _init?: RequestInit) =>
        new Response("pdf-ficticio", {
          status: 200,
          headers: { "content-type": "application/pdf" },
        }),
    );
    const client = new ApiClient({
      baseUrl: "http://api.test",
      store: seededStore(),
      fetchImpl,
    });

    const blob = await client.download("/api/movimientos-cc/m-1/recibo");

    expect(blob.type).toBe("application/pdf");
    expect(await blob.text()).toBe("pdf-ficticio");
    const init = fetchImpl.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(new Headers(init?.headers).get("authorization")).toBe("Bearer access-c15");
  });
});

describe("ApiClient errores de dominio (C-15)", () => {
  it("propaga el detail del backend en un 409", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(409, { detail: "transicion invalida desde atendido" }),
    );
    const client = new ApiClient({
      baseUrl: "http://api.test",
      store: seededStore(),
      fetchImpl,
    });

    await expect(client.patch("/api/turnos/t-1/estado", {})).rejects.toMatchObject({
      status: 409,
      message: "transicion invalida desde atendido",
    });
  });
});
