/** C-15: agenda usa el api-client autenticado para cambiar estado. Datos ficticios. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AUTH_STORAGE_KEY } from "../../shared/storage";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("agenda-api.cambiarEstado (C-15)", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("envía PATCH autenticado con el estado", async () => {
    localStorage.setItem(
      AUTH_STORAGE_KEY,
      JSON.stringify({ accessToken: "access-agenda" }),
    );
    const fetchImpl = vi.fn(
      async (_input: string | URL | Request, _init?: RequestInit) =>
        jsonResponse(200, { id: "t-1", estado: "atendido" }),
    );
    vi.stubGlobal("fetch", fetchImpl);

    const { cambiarEstado } = await import("./agenda-api");
    const data = await cambiarEstado("t-1", "atendido");

    expect(data).toEqual({ id: "t-1", estado: "atendido" });
    const [url, init] = fetchImpl.mock.calls[0] as [string | URL | Request, RequestInit?];
    expect(String(url)).toContain("/api/turnos/t-1/estado");
    expect(init?.method).toBe("PATCH");
    expect(new Headers(init?.headers).get("authorization")).toBe("Bearer access-agenda");
    expect(JSON.parse(String(init?.body))).toEqual({ estado: "atendido" });
  });

  it("propaga el detail 409 de una transición inválida", async () => {
    localStorage.setItem(
      AUTH_STORAGE_KEY,
      JSON.stringify({ accessToken: "access-agenda" }),
    );
    const fetchImpl = vi.fn(async () =>
      jsonResponse(409, { detail: "transicion invalida desde atendido" }),
    );
    vi.stubGlobal("fetch", fetchImpl);

    const { cambiarEstado } = await import("./agenda-api");

    await expect(cambiarEstado("t-2", "confirmado")).rejects.toMatchObject({
      status: 409,
      message: "transicion invalida desde atendido",
    });
  });
});
