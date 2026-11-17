/** C-15 task 4.2: patient list, search, pagination and ficha navigation. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { PacientesPage } from "./PacientesPage";
import { jsonResponse, seedSession, stubFetch } from "./clinica-test-utils";

function paciente(id: string, nombre: string): Record<string, unknown> {
  return {
    id,
    tenant_id: "t-ficticio-1",
    nombre,
    telefono: "555-0000",
    dni: `DNI-${id}`,
    email: null,
    obra_social: null,
    consentimiento_datos: true,
    is_active: true,
    created_at: "2030-01-01T10:00:00Z",
  };
}

function renderPage(): void {
  render(
    <MemoryRouter initialEntries={["/pacientes"]}>
      <Routes>
        <Route path="/pacientes" element={<PacientesPage />} />
        <Route path="/pacientes/:id" element={<p>Ficha abierta</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("PacientesPage (C-15 4.2)", () => {
  beforeEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
    seedSession();
  });

  it("crea un paciente, registra consentimiento y permite abrir su ficha", async () => {
    let saved = false;
    let payload: Record<string, unknown> = {};
    stubFetch((url, init) => {
      if (init?.method === "POST" && url.endsWith("/api/pacientes")) {
        payload = JSON.parse(String(init.body));
        saved = true;
        return jsonResponse(201, { ...paciente("nuevo", "Paciente Ficticio"), ...payload });
      }
      return jsonResponse(200, saved ? [paciente("nuevo", "Paciente Ficticio")] : []);
    });
    renderPage();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Nuevo paciente" }));
    await user.type(screen.getByLabelText("Nombre y apellido"), "  Paciente Ficticio  ");
    await user.type(screen.getByLabelText("Teléfono"), "0000000000");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Guardar paciente" }));
    expect(await screen.findByText("Paciente Ficticio")).toBeInTheDocument();
    expect(payload).toMatchObject({ nombre: "Paciente Ficticio", telefono: "0000000000", dni: null, email: null, obra_social: null, consentimiento_datos: true });
    expect(Number.isNaN(Date.parse(String(payload.consentimiento_at)))).toBe(false);
    await user.click(screen.getByRole("button", { name: "Abrir ficha de Paciente Ficticio" }));
    expect(await screen.findByText("Ficha abierta")).toBeInTheDocument();
  });

  it("conserva los datos ante DNI duplicado y permite cancelar sin guardar", async () => {
    let payload: Record<string, unknown> = {};
    const fetchImpl = stubFetch((_url, init) => {
      if (init?.method === "POST") {
        payload = JSON.parse(String(init.body));
        return jsonResponse(409, { detail: "dni duplicado en el tenant" });
      }
      return jsonResponse(200, []);
    });
    renderPage();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Nuevo paciente" }));
    await user.type(screen.getByLabelText("Nombre y apellido"), "Paciente Ficticio");
    await user.type(screen.getByLabelText("Teléfono"), "0000000000");
    await user.type(screen.getByLabelText("DNI"), "FICTICIO-01");
    await user.click(screen.getByRole("button", { name: "Guardar paciente" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Ya existe un paciente con ese DNI");
    expect(screen.getByLabelText("DNI")).toHaveValue("FICTICIO-01");
    expect(payload).toMatchObject({ consentimiento_datos: false, consentimiento_at: null });
    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByLabelText("Nombre y apellido")).not.toBeInTheDocument();
    expect(fetchImpl.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  });

  it("muestra los pacientes del tenant con su DNI", async () => {
    stubFetch((url) => {
      if (url.includes("/api/pacientes?")) {
        return jsonResponse(200, [paciente("p-1", "Pérez Ficticio")]);
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    renderPage();

    expect(await screen.findByText("Pérez Ficticio")).toBeInTheDocument();
    expect(screen.getByText("DNI-p-1")).toBeInTheDocument();
  });

  it("busca por apellido ficticio y refleja el estado vacío", async () => {
    const fetchImpl = stubFetch((url) => {
      if (url.includes("/api/pacientes?")) {
        const q = new URL(url).searchParams.get("q");
        return jsonResponse(
          200,
          q === null ? [paciente("p-1", "Pérez Ficticio")] : [],
        );
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    renderPage();
    const userEv = userEvent.setup();
    await userEv.type(screen.getByLabelText(/buscar paciente/i), "Gómez");

    await waitFor(() => {
      expect(
        screen.getByText("No hay pacientes que coincidan con la búsqueda."),
      ).toBeInTheDocument();
    });
    const urls = fetchImpl.mock.calls.map(([input]) => String(input));
    expect(urls.some((url) => url.includes("q=G%C3%B3mez"))).toBe(true);
  });

  it("pagina con offset y abre la ficha del paciente", async () => {
    const rows = Array.from({ length: 20 }, (_, index) =>
      paciente(`p-${index}`, `Paciente Ficticio ${index}`),
    );
    const fetchImpl = stubFetch((url) => {
      if (url.includes("/api/pacientes?")) {
        return jsonResponse(200, rows);
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    renderPage();
    const userEv = userEvent.setup();
    await screen.findByText("Paciente Ficticio 0");

    await userEv.click(screen.getByRole("button", { name: "Siguiente" }));
    await waitFor(() => {
      const urls = fetchImpl.mock.calls.map(([input]) => String(input));
      expect(urls.some((url) => url.includes("offset=20"))).toBe(true);
    });

    await userEv.click(
      screen.getAllByRole("button", { name: "Abrir ficha" })[0],
    );
    expect(await screen.findByText("Ficha abierta")).toBeInTheDocument();
  });
});
