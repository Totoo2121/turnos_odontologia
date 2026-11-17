/** C-15: clinical API client with fetch mocked. Datos ficticios. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../shared/api-client";
import { AUTH_STORAGE_KEY } from "../../shared/storage";
import {
  abrirHistoria,
  aceptarPresupuesto,
  crearEvolucion,
  crearEventoPieza,
  crearPresupuesto,
  descargarConsentimientoPdf,
  listPacientes,
  mensajeError,
  subirAdjunto,
  urlAdjunto,
  validarEventoPieza,
} from "./clinica-api";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

type FetchCall = [string | URL | Request, RequestInit | undefined];

function calls(fetchImpl: ReturnType<typeof vi.fn>): FetchCall[] {
  return fetchImpl.mock.calls as FetchCall[];
}

describe("clinica-api (C-15)", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
    localStorage.setItem(
      AUTH_STORAGE_KEY,
      JSON.stringify({ accessToken: "access-clinica" }),
    );
  });

  it("busca pacientes con q codificado y Authorization", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, []));
    vi.stubGlobal("fetch", fetchImpl);

    await listPacientes("Pérez Ficticio");

    const [url, init] = calls(fetchImpl)[0];
    expect(String(url)).toContain("q=P%C3%A9rez+Ficticio");
    expect(new Headers(init?.headers).get("authorization")).toBe(
      "Bearer access-clinica",
    );
  });

  it("abre la historia con POST idempotente", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(201, { id: "h-1", paciente_id: "p-1" }),
    );
    vi.stubGlobal("fetch", fetchImpl);

    await abrirHistoria("p-1");

    const [url, init] = calls(fetchImpl)[0];
    expect(String(url)).toContain("/api/historias-clinicas");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ paciente_id: "p-1" });
  });

  it("registra una corrección con corrige_evolucion_id", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(201, { id: "e-2", contenido: "Corrección ficticia" }),
    );
    vi.stubGlobal("fetch", fetchImpl);

    await crearEvolucion("h-1", "Corrección ficticia", "e-1");

    const [url, init] = calls(fetchImpl)[0];
    expect(String(url)).toContain("/api/historias-clinicas/h-1/evoluciones");
    expect(JSON.parse(String(init?.body))).toEqual({
      contenido: "Corrección ficticia",
      corrige_evolucion_id: "e-1",
    });
  });

  it("registra un evento de pieza con superficie", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(201, { id: "ev-1", pieza_fdi: 16, estado: "caries" }),
    );
    vi.stubGlobal("fetch", fetchImpl);

    await crearEventoPieza("h-1", {
      pieza_fdi: 16,
      estado: "caries",
      superficie: "oclusal",
    });

    const [url, init] = calls(fetchImpl)[0];
    expect(String(url)).toContain("/api/odontogramas/h-1/eventos");
    expect(JSON.parse(String(init?.body))).toEqual({
      pieza_fdi: 16,
      estado: "caries",
      superficie: "oclusal",
    });
  });

  it("sube un adjunto multipart sin content-type manual ni turno_id", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(201, { id: "a-1" }));
    vi.stubGlobal("fetch", fetchImpl);
    const archivo = new File(["rx-ficticia"], "rx-ficticia.pdf", {
      type: "application/pdf",
    });

    await subirAdjunto("h-1", {
      tipo: "rx",
      archivo,
      origen: "consulta",
    });

    const [url, init] = calls(fetchImpl)[0];
    expect(String(url)).toContain("/api/historias-clinicas/h-1/adjuntos");
    const form = init?.body as FormData;
    expect(form.get("tipo")).toBe("rx");
    expect(form.get("origen")).toBe("consulta");
    expect(form.get("turno_id")).toBeNull();
    expect(new Headers(init?.headers).get("content-type")).toBeNull();
  });

  it("solicita la URL firmada de un adjunto sin exponer storage_key", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(200, {
        url: "http://storage.test/firmada",
        expires_at: "2030-01-01T00:00:00Z",
      }),
    );
    vi.stubGlobal("fetch", fetchImpl);

    const data = await urlAdjunto("a-1");

    expect(data.url).toContain("firmada");
    const [url] = calls(fetchImpl)[0];
    expect(String(url)).toContain("/api/adjuntos/a-1/url");
    expect(String(url)).not.toContain("storage_key");
  });

  it("arma un presupuesto con dos ítems y total del servidor", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(201, {
        id: "pr-1",
        estado: "borrador",
        total: "25000.00",
        items: [{ id: "i-1" }, { id: "i-2" }],
      }),
    );
    vi.stubGlobal("fetch", fetchImpl);

    const data = await crearPresupuesto({
      paciente_id: "p-1",
      historia_clinica_id: "h-1",
      observaciones: null,
      items: [
        { prestacion_id: "prest-1", cantidad: 1, etapa: 1 },
        {
          prestacion_id: "prest-2",
          cantidad: 2,
          etapa: 2,
          pieza_fdi: 16,
          superficie: "oclusal",
        },
      ],
    });

    expect(data.total).toBe("25000.00");
    const [, init] = calls(fetchImpl)[0];
    const body = JSON.parse(String(init?.body)) as { items: unknown[] };
    expect(body.items).toHaveLength(2);
  });

  it("traduce el 409 consentimiento_requerido", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(409, { detail: "consentimiento_requerido" }),
    );
    vi.stubGlobal("fetch", fetchImpl);

    await expect(aceptarPresupuesto("pr-1")).rejects.toMatchObject({
      status: 409,
      message: "consentimiento_requerido",
    });
    expect(
      mensajeError(new ApiError(409, "consentimiento_requerido")),
    ).toBe("El presupuesto requiere un consentimiento invasivo firmado.");
  });

  it("descarga el PDF del consentimiento autenticado", async () => {
    const fetchImpl = vi.fn(
      async (_input: string | URL | Request, _init?: RequestInit) =>
        new Response("pdf-ficticio", {
          status: 200,
          headers: { "content-type": "application/pdf" },
        }),
    );
    vi.stubGlobal("fetch", fetchImpl);

    const blob = await descargarConsentimientoPdf("c-1");

    expect(blob.type).toBe("application/pdf");
    const [url, init] = calls(fetchImpl)[0];
    expect(String(url)).toContain("/api/consentimientos/c-1/pdf");
    expect(new Headers(init?.headers).get("authorization")).toBe(
      "Bearer access-clinica",
    );
  });

  it("valida la tabla estado-superficie antes de llamar a la API", () => {
    expect(validarEventoPieza("caries", null)).toContain("requiere");
    expect(validarEventoPieza("corona", "oclusal")).toContain("no admite");
    expect(validarEventoPieza("caries", "oclusal")).toBeNull();
    expect(validarEventoPieza("corona", null)).toBeNull();
  });

  it("mensajeError oculta detalles en 403 y 404", () => {
    expect(mensajeError(new ApiError(403, "forbidden"))).toBe(
      "No tenés permiso para esta acción.",
    );
    expect(mensajeError(new ApiError(404, "not found"))).toBe(
      "No se encontró el recurso en este tenant.",
    );
  });
});
