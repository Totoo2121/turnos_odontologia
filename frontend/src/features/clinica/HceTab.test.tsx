/** C-15 task 4.4: HCE append-only evolutions and corrections. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HceTab } from "./HceTab";
import {
  callsFor,
  jsonResponse,
  seedSession,
  stubFetch,
} from "./clinica-test-utils";

const HISTORIA = {
  id: "h-1",
  paciente_id: "p-1",
  alergias: "Ninguna",
  medicacion: null,
  antecedentes: null,
};

const EVOLUCIONES = [
  {
    id: "ev-1",
    historia_clinica_id: "h-1",
    autor_usuario_id: "u-ficticio-1",
    contenido: "Evolución ficticia inicial.",
    corrige_evolucion_id: null,
    created_at: "2030-01-02T10:00:00Z",
  },
  {
    id: "ev-2",
    historia_clinica_id: "h-1",
    autor_usuario_id: "u-ficticio-1",
    contenido: "Control ficticio sin dolor.",
    corrige_evolucion_id: null,
    created_at: "2030-01-03T10:00:00Z",
  },
];

describe("HceTab (C-15 4.4)", () => {
  beforeEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
    seedSession();
  });

  it("lista la anamnesis y las evoluciones con autor y fecha", async () => {
    stubFetch((url, init) => {
      const method = init?.method ?? "GET";
      if (url.includes("/evoluciones") && method === "GET") {
        return jsonResponse(200, EVOLUCIONES);
      }
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });

    render(<HceTab historia={HISTORIA} canWrite />);

    expect(await screen.findByText("Evolución ficticia inicial.")).toBeInTheDocument();
    expect(screen.getByText("Control ficticio sin dolor.")).toBeInTheDocument();
    expect(screen.getAllByText(/Autor: u-fictic/)).toHaveLength(2);
    expect(screen.getByText("Ninguna")).toBeInTheDocument();
  });

  it("agrega una evolución nueva con el contenido escrito", async () => {
    const fetchImpl = stubFetch((url, init) => {
      const method = init?.method ?? "GET";
      if (url.includes("/evoluciones") && method === "GET") {
        return jsonResponse(200, EVOLUCIONES);
      }
      if (url.includes("/evoluciones") && method === "POST") {
        return jsonResponse(201, {
          id: "ev-3",
          historia_clinica_id: "h-1",
          autor_usuario_id: "u-ficticio-1",
          contenido: "Alta ficticia de evolución.",
          corrige_evolucion_id: null,
          created_at: "2030-01-04T10:00:00Z",
        });
      }
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });

    render(<HceTab historia={HISTORIA} canWrite />);
    const userEv = userEvent.setup();
    await screen.findByText("Evolución ficticia inicial.");

    await userEv.type(
      screen.getByLabelText("Nueva evolución"),
      "Alta ficticia de evolución.",
    );
    await userEv.click(screen.getByRole("button", { name: "Agregar evolución" }));

    expect(
      await screen.findByText("Alta ficticia de evolución."),
    ).toBeInTheDocument();
    const [, init] = callsFor(fetchImpl, "POST")[0];
    expect(JSON.parse(String(init?.body))).toEqual({
      contenido: "Alta ficticia de evolución.",
      corrige_evolucion_id: null,
    });
  });

  it("corrige con una evolución nueva y no ofrece editar ni borrar", async () => {
    const fetchImpl = stubFetch((url, init) => {
      const method = init?.method ?? "GET";
      if (url.includes("/evoluciones") && method === "GET") {
        return jsonResponse(200, EVOLUCIONES);
      }
      if (url.includes("/evoluciones") && method === "POST") {
        return jsonResponse(201, {
          id: "ev-4",
          historia_clinica_id: "h-1",
          autor_usuario_id: "u-ficticio-1",
          contenido: "Corrección ficticia.",
          corrige_evolucion_id: "ev-1",
          created_at: "2030-01-05T10:00:00Z",
        });
      }
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });

    render(<HceTab historia={HISTORIA} canWrite />);
    const userEv = userEvent.setup();
    await screen.findByText("Evolución ficticia inicial.");

    expect(
      screen.queryByRole("button", {
        name: /editar evolución|eliminar evolución|borrar evolución/i,
      }),
    ).not.toBeInTheDocument();

    await userEv.click(
      screen.getAllByRole("button", { name: "Corregir evolución" })[0],
    );
    expect(screen.getByLabelText("Corrección de evolución")).toBeInTheDocument();
    await userEv.type(
      screen.getByLabelText("Corrección de evolución"),
      "Corrección ficticia.",
    );
    await userEv.click(
      screen.getByRole("button", { name: "Registrar corrección" }),
    );

    await waitFor(() => {
      expect(screen.getByText("Corrección ficticia.")).toBeInTheDocument();
    });
    expect(screen.getByText("Evolución ficticia inicial.")).toBeInTheDocument();
    const [, init] = callsFor(fetchImpl, "POST")[0];
    expect(JSON.parse(String(init?.body))).toEqual({
      contenido: "Corrección ficticia.",
      corrige_evolucion_id: "ev-1",
    });
  });
});
