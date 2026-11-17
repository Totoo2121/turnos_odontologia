/** C-15 task 4.8: signed consents, hash status and PDF download. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConsentimientosTab } from "./ConsentimientosTab";
import {
  callsFor,
  jsonResponse,
  pdfResponse,
  seedSession,
  stubFetch,
} from "./clinica-test-utils";

const CONSENTIMIENTO = {
  id: "c-1",
  paciente_id: "p-1",
  historia_clinica_id: "h-1",
  tipo: "tratamiento",
  texto_version: "v1",
  texto: "Texto ficticio del consentimiento informado.",
  plan_invasivo: false,
  firmante_nombre: "Firmante Ficticio",
  firmante_dni: "DNI-000",
  firmado_at: "2030-01-10T10:00:00Z",
  firma_hash: "hash-ficticio",
  hash_valido: true,
};

describe("ConsentimientosTab (C-15 4.8)", () => {
  beforeEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
    seedSession();
  });

  it("firma un consentimiento invasivo y lo lista con hash verificado", async () => {
    const fetchImpl = stubFetch((url, init) => {
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/pacientes/p-1/consentimientos") && method === "GET") {
        return jsonResponse(200, []);
      }
      if (url.endsWith("/api/consentimientos") && method === "POST") {
        return jsonResponse(201, {
          ...CONSENTIMIENTO,
          id: "c-2",
          tipo: "invasivo",
          plan_invasivo: true,
        });
      }
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });

    render(
      <ConsentimientosTab pacienteId="p-1" historiaId="h-1" canWrite />,
    );
    const userEv = userEvent.setup();
    await screen.findByText("Todavía no hay consentimientos firmados.");

    await userEv.selectOptions(screen.getByLabelText("Tipo"), "invasivo");
    await userEv.type(
      screen.getByLabelText("Texto del consentimiento"),
      "Texto ficticio del consentimiento informado.",
    );
    await userEv.type(screen.getByLabelText("Firmante"), "Firmante Ficticio");
    await userEv.click(
      screen.getByRole("button", { name: "Firmar consentimiento" }),
    );

    expect(await screen.findByText("Hash verificado")).toBeInTheDocument();
    expect(screen.getByText("Firmante: Firmante Ficticio")).toBeInTheDocument();
    const [, init] = callsFor(fetchImpl, "POST")[0];
    expect(JSON.parse(String(init?.body))).toMatchObject({
      historia_clinica_id: "h-1",
      tipo: "invasivo",
      texto_version: "v1",
      plan_invasivo: true,
    });
  });

  it("firma incompleta no llama a la API", async () => {
    const fetchImpl = stubFetch((url, init) => {
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/pacientes/p-1/consentimientos") && method === "GET") {
        return jsonResponse(200, []);
      }
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });

    render(
      <ConsentimientosTab pacienteId="p-1" historiaId="h-1" canWrite />,
    );
    const userEv = userEvent.setup();
    await screen.findByText("Todavía no hay consentimientos firmados.");

    await userEv.click(
      screen.getByRole("button", { name: "Firmar consentimiento" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "El texto del consentimiento es obligatorio.",
    );
    expect(callsFor(fetchImpl, "POST")).toHaveLength(0);
  });

  it("descarga el PDF autenticado del consentimiento", async () => {
    const createObjectURL = vi.fn((_blob: Blob) => "blob:ficticio");
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: createObjectURL,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    stubFetch((url, init) => {
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/pacientes/p-1/consentimientos") && method === "GET") {
        return jsonResponse(200, [CONSENTIMIENTO]);
      }
      if (url.endsWith("/api/consentimientos/c-1/pdf") && method === "GET") {
        return pdfResponse();
      }
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });

    render(
      <ConsentimientosTab pacienteId="p-1" historiaId="h-1" canWrite={false} />,
    );
    const userEv = userEvent.setup();
    await screen.findByText("Firmante: Firmante Ficticio");

    await userEv.click(screen.getByRole("button", { name: "Abrir PDF" }));

    await waitFor(() => {
      expect(createObjectURL).toHaveBeenCalledTimes(1);
    });
    const blob = createObjectURL.mock.calls[0][0] as Blob;
    expect(blob.type).toBe("application/pdf");
  });
});
