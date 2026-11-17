/** C-15 task 4.3: ficha administrative block + role-gated clinical tabs. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { useAuthStore, type Role } from "../auth/auth-store";
import { PacienteFichaPage } from "./PacienteFichaPage";
import {
  jsonResponse,
  seedSession,
  stubFetch,
  type FetchHandler,
} from "./clinica-test-utils";

const PACIENTE = {
  id: "p-1",
  tenant_id: "t-ficticio-1",
  nombre: "Paciente Ficticio",
  telefono: "555-0100",
  dni: "DNI-000",
  email: null,
  obra_social: null,
  consentimiento_datos: true,
  is_active: true,
  created_at: "2030-01-01T10:00:00Z",
};

const HISTORIA = {
  id: "h-1",
  tenant_id: "t-ficticio-1",
  paciente_id: "p-1",
  alergias: "Ninguna",
  medicacion: null,
  antecedentes: null,
  created_at: "2030-01-01T10:00:00Z",
};

function presetSession(roles: Role[]): void {
  useAuthStore.setState({
    accessToken: "access-clinica-test",
    user: {
      id: "u-ficticia-1",
      email: "staff@ficticio.test",
      roles,
      tenantId: "t-ficticio-1",
    },
    status: "authenticated",
    error: null,
  });
}

function baseHandler(clinicalAccess: boolean): FetchHandler {
  return (url, init) => {
    const method = init?.method ?? "GET";
    if (url.endsWith("/api/pacientes/p-1") && method === "GET") {
      return jsonResponse(200, PACIENTE);
    }
    if (url.endsWith("/api/historias-clinicas") && method === "POST") {
      return clinicalAccess
        ? jsonResponse(201, HISTORIA)
        : jsonResponse(403, { detail: "forbidden" });
    }
    if (url.includes("/api/historias-clinicas/h-1/evoluciones")) {
      return jsonResponse(200, []);
    }
    if (url.includes("/api/turnos/agenda")) {
      return jsonResponse(200, []);
    }
    if (url.endsWith("/api/prestaciones")) {
      return jsonResponse(200, []);
    }
    if (url.endsWith("/api/profesionales") || url.endsWith("/api/sillones")) {
      return jsonResponse(200, []);
    }
    throw new Error(`unexpected fetch: ${method} ${url}`);
  };
}

function renderFicha(): void {
  render(
    <MemoryRouter initialEntries={["/pacientes/p-1"]}>
      <Routes>
        <Route path="/pacientes/:id" element={<PacienteFichaPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("PacienteFichaPage (C-15 4.3)", () => {
  beforeEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
    seedSession();
    useAuthStore.setState({
      accessToken: null,
      user: null,
      status: "unauthenticated",
      error: null,
    });
  });

  it("odontólogo con acceso ve el bloque administrativo y las cinco pestañas", async () => {
    presetSession(["odontologo"]);
    stubFetch(baseHandler(true));

    renderFicha();

    expect(await screen.findByText("Paciente Ficticio")).toBeInTheDocument();
    expect(screen.getByText("DNI-000")).toBeInTheDocument();
    for (const label of [
      "HCE",
      "Odontograma",
      "Adjuntos",
      "Presupuestos",
      "Consentimientos",
    ]) {
      expect(await screen.findByRole("tab", { name: label })).toBeInTheDocument();
    }
  });

  it("recepción ve solo el bloque administrativo", async () => {
    presetSession(["recepcion"]);
    stubFetch(baseHandler(false));

    renderFicha();

    expect(await screen.findByText("Paciente Ficticio")).toBeInTheDocument();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    expect(
      screen.getByText(/solo están disponibles para el odontólogo tratante/i),
    ).toBeInTheDocument();
  });

  it("asistente no ve pestañas clínicas", async () => {
    presetSession(["asistente"]);
    stubFetch(baseHandler(false));

    renderFicha();

    expect(await screen.findByText("Paciente Ficticio")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "HCE" })).not.toBeInTheDocument();
  });

  it("profesional ajeno recibe el aviso de acceso clínico restringido", async () => {
    presetSession(["odontologo"]);
    stubFetch(baseHandler(false));

    renderFicha();

    expect(
      await screen.findByText(/Acceso clínico restringido/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    expect(screen.queryByText("Evoluciones")).not.toBeInTheDocument();
  });
});
