/** C-15 task 3.3: real routes for patients/ficha/caja, placeholders for the rest. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AppRoutes } from "./router";
import { useAuthStore, type Role } from "../features/auth/auth-store";
import {
  jsonResponse,
  stubFetch,
} from "../features/clinica/clinica-test-utils";

const PACIENTE = {
  id: "p-1",
  nombre: "Paciente Ficticio R",
  telefono: "555-0000",
  dni: "DNI-R",
  email: null,
  obra_social: null,
  consentimiento_datos: true,
  is_active: true,
  created_at: "2030-01-01T10:00:00Z",
};

function cierreVacio(): Record<string, unknown> {
  return {
    fecha: "2030-01-10",
    moneda: "ARS",
    cobrado_total: "0.00",
    por_medio: {},
    cantidad_pagos: 0,
    deuda_generada: "0.00",
    diferencia_caja: "0.00",
    turnos_atendidos: 0,
    movimientos: [],
    turnos: [],
  };
}

function presetSession(roles: Role[] | null): void {
  if (roles === null) {
    useAuthStore.setState({
      accessToken: null,
      user: null,
      status: "unauthenticated",
      error: null,
    });
  } else {
    useAuthStore.setState({
      accessToken: "access-ficticio-r",
      user: {
        id: "u-ficticia-r",
        email: "recepcion@ficticio.test",
        roles,
        tenantId: "t-ficticio-1",
      },
      status: "authenticated",
      error: null,
    });
  }
}

function renderPath(path: string): void {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe("router C-15 (3.3)", () => {
  beforeEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
    useAuthStore.setState({
      accessToken: null,
      user: null,
      status: "unauthenticated",
      error: null,
    });
  });

  it("recepción en /agenda ve la agenda real dentro del shell", async () => {
    presetSession(["recepcion"]);
    stubFetch(async () => jsonResponse(200, {}));
    renderPath("/agenda");

    expect(
      await screen.findByRole("heading", { name: "Agenda" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: /principal/i }),
    ).toBeInTheDocument();
  });

  it("anónimo en /agenda ve el login", () => {
    presetSession(null);
    renderPath("/agenda");

    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("navigation", { name: /principal/i }),
    ).not.toBeInTheDocument();
  });

  it("renderiza la lista real de pacientes y la ficha en /pacientes/:id", async () => {
    presetSession(["asistente"]);
    stubFetch(async (url) => {
      if (url.includes("/api/pacientes?") || url.endsWith("/api/pacientes/p-1")) {
        return jsonResponse(200, url.includes("/api/pacientes?") ? [PACIENTE] : PACIENTE);
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    renderPath("/pacientes");
    expect(
      await screen.findByRole("heading", { name: "Pacientes" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Paciente Ficticio R")).toBeInTheDocument();
    cleanup();

    renderPath("/pacientes/p-1");
    expect(
      await screen.findByRole("heading", { name: "Paciente Ficticio R" }),
    ).toBeInTheDocument();
    expect(screen.getByText("DNI-R")).toBeInTheDocument();
  });

  it("recepción en /caja ve la caja real y el cierre del día", async () => {
    presetSession(["recepcion"]);
    stubFetch(async (url) => {
      if (url.includes("/api/caja/cierre")) {
        return jsonResponse(200, cierreVacio());
      }
      if (url.includes("/api/turnos/agenda")) {
        return jsonResponse(200, []);
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    renderPath("/caja");

    expect(
      await screen.findByRole("heading", { name: "Caja" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Cierre de caja")).toBeInTheDocument();
  });

  it("asistente en /caja va a /403 y no consulta la cuenta corriente", async () => {
    presetSession(["asistente"]);
    const fetchImpl = stubFetch(async (url) => {
      throw new Error(`unexpected fetch: ${url}`);
    });

    renderPath("/caja");

    expect(await screen.findByText(/sin permiso/i)).toBeInTheDocument();
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("muestra reportes y carga el panel funcional de administración del propietario", async () => {
    presetSession(["propietario"]);
    stubFetch(async (url) => {
      if (url.includes("/api/reportes/ocupacion")) return jsonResponse(200, { desde: "2030-01-01", hasta: "2030-01-10", alcance: "total", filas: [] });
      if (url.includes("/api/reportes/ausentismo")) return jsonResponse(200, { desde: "2030-01-01", hasta: "2030-01-10", alcance: "total", filas: [] });
      if (url.includes("/api/reportes/recaudacion")) return jsonResponse(200, { desde: "2030-01-01", hasta: "2030-01-10", alcance: "total", senias_acreditadas: "0", cobros_cuenta_corriente: "0", total_cobrado: "0", cantidad_cobros_cuenta_corriente: 0, deuda_neta_planes: "0", por_profesional: [] });
      throw new Error(`unexpected fetch: ${url}`);
    });

    renderPath("/reportes");
    expect(await screen.findByRole("heading", { name: "Reportes" })).toBeInTheDocument();
    cleanup();

    let profile = { id: "t-ficticio-1", nombre: "Clínica Demo", slug_reserva: "demo-ficticia", moneda: "ARS" };
    const team = [{ id: "u-owner", email: "dueno@example.invalid", nombre: "Dueño ficticio", rol: "propietario", activo: true, created_at: "2030-01-01T10:00:00Z" }];
    const jobs: Array<{ id: string; estado: string; solicitada_at: string; generada_at: null; vence_at: null }> = [];
    stubFetch(async (url, init) => {
      if (url.endsWith("/api/admin/perfil") && init?.method === "PATCH") {
        profile = { ...profile, ...(JSON.parse(String(init.body)) as { nombre: string }) };
        return jsonResponse(200, profile);
      }
      if (url.endsWith("/api/admin/perfil")) return jsonResponse(200, profile);
      if (url.endsWith("/api/admin/usuarios") && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as { email: string; nombre: string; rol: string };
        team.push({ id: "u-created", email: body.email, nombre: body.nombre, rol: body.rol, activo: true, created_at: "2030-01-02T10:00:00Z" });
        return jsonResponse(201, team[1]);
      }
      if (url.endsWith("/api/admin/usuarios")) return jsonResponse(200, team);
      if (url.includes("/api/admin/auditoria")) return jsonResponse(200, []);
      if (url.endsWith("/api/admin/exportacion") && init?.method === "POST") {
        const job = { id: "export-ficticia-1", estado: "pendiente", solicitada_at: "2030-01-02T10:00:00Z", generada_at: null, vence_at: null };
        jobs.unshift(job);
        return jsonResponse(202, job);
      }
      if (url.endsWith("/api/admin/exportaciones")) return jsonResponse(200, jobs);
      throw new Error(`unexpected fetch: ${url}`);
    });
    renderPath("/admin");
    expect(await screen.findByRole("heading", { name: "Administración" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Perfil de la clínica" })).toBeInTheDocument();
    expect(screen.getByText("demo-ficticia", { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Equipo" })).toBeInTheDocument();
    expect(screen.getByText("dueno@example.invalid")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Auditoría reciente" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Exportación de datos" })).toBeInTheDocument();
    expect(screen.queryByText(/contenido en su change/i)).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Nombre de la clínica"), { target: { value: "Consultorio Demo" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));
    expect(await screen.findByText("Datos de la clínica actualizados.")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Nombre", { selector: "input" }), { target: { value: "Recepción Demo" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "recepcion@demo-ficticia.invalid" } });
    fireEvent.change(screen.getByLabelText(/Contraseña inicial/), { target: { value: "Ficticia-Local-2030!" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear usuario" }));
    expect(await screen.findByText("recepcion@demo-ficticia.invalid")).toBeInTheDocument();
    expect(await screen.findByText(/compartí la contraseña inicial/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Solicitar exportación" }));
    expect(await screen.findByText("pendiente")).toBeInTheDocument();
    expect(await screen.findByText(/exportación solicitada/i)).toBeInTheDocument();
  });

  it("bloquea administración para recepción sin consultar la API", async () => {
    presetSession(["recepcion"]);
    const fetchImpl = stubFetch(async (url) => { throw new Error(`unexpected fetch: ${url}`); });
    renderPath("/admin");
    expect(await screen.findByText(/sin permiso/i)).toBeInTheDocument();
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});
