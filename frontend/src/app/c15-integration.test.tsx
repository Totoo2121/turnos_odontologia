/** C-15 task 6.3: routed frontend integration with a stateful mocked API.
 * Covers the consent gate → plan/debt flow and the role matrix in counter cash.
 * Datos 100% ficticios.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AppRoutes } from "./router";
import { useAuthStore, type Role } from "../features/auth/auth-store";
import {
  jsonResponse,
  seedSession,
  stubFetch,
} from "../features/clinica/clinica-test-utils";

const PACIENTE = {
  id: "p-1",
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
  paciente_id: "p-1",
  alergias: "Ninguna",
  medicacion: null,
  antecedentes: null,
};

const PRESTACION = {
  id: "prest-2",
  nombre: "Obturación ficticia",
  duracion_min: 45,
  buffer_min: 10,
  precio: "25000.00",
  requiere_consentimiento: true,
  intervalo_control_dias: 180,
  is_active: true,
};

const ITEM = {
  id: "i-1",
  presupuesto_id: "pr-1",
  prestacion_id: "prest-2",
  descripcion: "Obturación ficticia",
  cantidad: 1,
  precio_unitario: "25000.00",
  importe: "25000.00",
  etapa: 1,
  requiere_consentimiento: true,
  pieza_fdi: 16,
  superficie: "oclusal",
};

function presupuesto(estado: string): Record<string, unknown> {
  return {
    id: "pr-1",
    paciente_id: "p-1",
    historia_clinica_id: "h-1",
    estado,
    moneda: "ARS",
    total: "25000.00",
    validez_hasta: null,
    observaciones: "Presupuesto ficticio",
    created_at: "2030-01-10T10:00:00Z",
    items: [ITEM],
  };
}

const CONSENTIMIENTO = {
  id: "c-1",
  paciente_id: "p-1",
  historia_clinica_id: "h-1",
  tipo: "invasivo",
  texto_version: "v1",
  texto: "Texto ficticio del consentimiento informado.",
  plan_invasivo: true,
  firmante_nombre: "Firmante Ficticio",
  firmante_dni: "DNI-000",
  firmado_at: "2030-01-10T10:00:00Z",
  firma_hash: "hash-ficticio",
  hash_valido: true,
};

const PLAN = {
  id: "plan-1",
  presupuesto_id: "pr-1",
  paciente_id: "p-1",
  consentimiento_id: "c-1",
  estado: "activo",
  total: "25000.00",
  etapas: 1,
  etapa_actual: 1,
  detalle: [{ etapa: 1, subtotal: "25000.00", items: [ITEM] }],
};

const DEBITO = {
  id: "mov-1",
  tipo: "debito",
  monto: "25000.00",
  descripcion: "Presupuesto aceptado",
  referencia: "presupuesto:pr-1",
  ocurrido_at: "2030-01-10T10:00:00Z",
};

const TURNO = {
  id: "t-1",
  inicio: "2030-01-10T12:00:00Z",
  fin: "2030-01-10T12:30:00Z",
  estado: "atendido",
  paciente_id: "p-1",
  profesional_id: "prof-1",
  sillon_id: "sil-1",
  cobro: "acreditado",
  cobro_monto: 5000,
};

function cierre(): Record<string, unknown> {
  return {
    fecha: "2030-01-10",
    moneda: "ARS",
    cobrado_total: "15000.00",
    por_medio: { efectivo: "15000.00" },
    cantidad_pagos: 1,
    deuda_generada: "25000.00",
    diferencia_caja: "-10000.00",
    turnos_atendidos: 1,
    movimientos: [DEBITO],
    turnos: [],
  };
}

function presetSession(roles: Role[]): void {
  seedSession();
  useAuthStore.setState({
    accessToken: "access-integracion",
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

function renderPath(path: string): void {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

async function buscarYSeleccionar(
  userEv: ReturnType<typeof userEvent.setup>,
): Promise<void> {
  await userEv.type(screen.getByRole("searchbox"), "Ficticio");
  await userEv.click(screen.getByRole("button", { name: "Buscar" }));
  await screen.findByText("Paciente Ficticio");
  await userEv.click(screen.getByRole("button", { name: "Ver cuenta" }));
  await screen.findByText("Cuenta corriente de Paciente Ficticio");
}

describe("C-15 integración frontend (6.3)", () => {
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

  it("ficha: 409 de consentimiento → firma → aceptación con plan y deuda", async () => {
    presetSession(["odontologo"]);
    let firmado = false;
    let aceptado = false;

    stubFetch(async (url, init) => {
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/pacientes/p-1") && method === "GET") {
        return jsonResponse(200, PACIENTE);
      }
      if (url.endsWith("/api/historias-clinicas") && method === "POST") {
        return jsonResponse(201, HISTORIA);
      }
      if (
        url.includes("/api/historias-clinicas/h-1/evoluciones") &&
        method === "GET"
      ) {
        return jsonResponse(200, []);
      }
      if (url.includes("/api/turnos/agenda") && method === "GET") {
        return jsonResponse(200, []);
      }
      if (url.endsWith("/api/prestaciones") && method === "GET") {
        return jsonResponse(200, [PRESTACION]);
      }
      if (url.includes("/api/presupuestos?") && method === "GET") {
        return jsonResponse(200, [
          presupuesto(aceptado ? "aceptado" : "enviado"),
        ]);
      }
      if (
        url.endsWith("/api/presupuestos/pr-1/aceptar") &&
        method === "POST"
      ) {
        if (!firmado) {
          return jsonResponse(409, { detail: "consentimiento_requerido" });
        }
        aceptado = true;
        return jsonResponse(200, {
          ...presupuesto("aceptado"),
          plan_id: "plan-1",
          movimiento_id: "mov-deuda",
        });
      }
      if (
        url.endsWith("/api/pacientes/p-1/consentimientos") &&
        method === "GET"
      ) {
        return jsonResponse(200, firmado ? [CONSENTIMIENTO] : []);
      }
      if (url.endsWith("/api/consentimientos") && method === "POST") {
        firmado = true;
        return jsonResponse(201, CONSENTIMIENTO);
      }
      if (
        url.endsWith("/api/planes-tratamiento/plan-1") &&
        method === "GET"
      ) {
        return jsonResponse(200, PLAN);
      }
      if (
        url.endsWith("/api/pacientes/p-1/cuenta-corriente") &&
        method === "GET"
      ) {
        return jsonResponse(200, {
          paciente_id: "p-1",
          moneda: "ARS",
          saldo: aceptado ? "25000.00" : "0.00",
          movimientos: aceptado ? [DEBITO] : [],
        });
      }
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });
    const userEv = userEvent.setup();

    renderPath("/pacientes/p-1");
    expect(
      await screen.findByRole("heading", { name: "Paciente Ficticio" }),
    ).toBeInTheDocument();

    await userEv.click(
      await screen.findByRole("tab", { name: "Presupuestos" }),
    );
    await userEv.click(
      await screen.findByRole("button", { name: "Aceptar presupuesto" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "El presupuesto requiere un consentimiento invasivo firmado.",
    );

    await userEv.click(screen.getByRole("tab", { name: "Consentimientos" }));
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

    await userEv.click(screen.getByRole("tab", { name: "Presupuestos" }));
    await userEv.click(
      await screen.findByRole("button", { name: "Aceptar presupuesto" }),
    );
    expect(
      await screen.findByText("Plan de tratamiento generado"),
    ).toBeInTheDocument();
    expect(screen.getByText(/La deuda quedó registrada/)).toBeInTheDocument();
    expect(screen.getByText(/Saldo: .*25\.000,00/)).toBeInTheDocument();
  });

  it("caja: recepción cobra; odontólogo no cobra y recepción no ve clínica", async () => {
    presetSession(["recepcion"]);

    stubFetch(async (url, init) => {
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/pacientes/p-1") && method === "GET") {
        return jsonResponse(200, PACIENTE);
      }
      if (url.includes("/api/turnos/agenda") && method === "GET") {
        return jsonResponse(200, []);
      }
      if (url.endsWith("/api/prestaciones") && method === "GET") {
        return jsonResponse(200, [PRESTACION]);
      }
      if (
        (url.endsWith("/api/profesionales") ||
          url.endsWith("/api/sillones")) &&
        method === "GET"
      ) {
        return jsonResponse(200, []);
      }
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });
    renderPath("/pacientes/p-1");
    expect(
      await screen.findByRole("heading", { name: "Paciente Ficticio" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    expect(
      screen.getByText(/solo están disponibles para el odontólogo tratante/i),
    ).toBeInTheDocument();
    cleanup();

    presetSession(["recepcion"]);
    let pagado = false;
    stubFetch(async (url, init) => {
      const method = init?.method ?? "GET";
      if (url.includes("/api/caja/cierre") && method === "GET") {
        return jsonResponse(200, cierre());
      }
      if (url.includes("/api/turnos/agenda") && method === "GET") {
        return jsonResponse(200, [TURNO]);
      }
      if (url.includes("/api/pacientes?") && method === "GET") {
        return jsonResponse(200, [PACIENTE]);
      }
      if (
        url.endsWith("/api/pacientes/p-1/cuenta-corriente") &&
        method === "GET"
      ) {
        return jsonResponse(200, {
          paciente_id: "p-1",
          moneda: "ARS",
          saldo: pagado ? "10000.00" : "25000.00",
          movimientos: [DEBITO],
        });
      }
      if (
        url.endsWith("/api/pacientes/p-1/cuenta-corriente/pagos") &&
        method === "POST"
      ) {
        pagado = true;
        return jsonResponse(201, {
          movimiento: {
            id: "mov-pago",
            tipo: "credito",
            monto: "15000.00",
            descripcion: "Cobro en Efectivo",
            referencia: "pago:efectivo:clave-integracion",
            ocurrido_at: "2030-01-10T12:00:00Z",
          },
          saldo: "10000.00",
          medio: "efectivo",
          referencia: "pago:efectivo:clave-integracion",
        });
      }
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });
    const userEv = userEvent.setup();
    renderPath("/caja");
    expect(
      await screen.findByRole("heading", { name: "Caja" }),
    ).toBeInTheDocument();
    await buscarYSeleccionar(userEv);
    await userEv.type(screen.getByLabelText("Monto"), "15000");
    await userEv.click(screen.getByRole("button", { name: "Registrar cobro" }));

    expect(
      await screen.findByText(/Cobro registrado con Efectivo/),
    ).toBeInTheDocument();
    const region = screen.getByRole("region", {
      name: "Cuenta corriente de Paciente Ficticio",
    });
    expect(within(region).getByText(/10\.000,00/)).toBeInTheDocument();
    expect(screen.getByText("Cierre de caja")).toBeInTheDocument();
    expect(screen.getAllByText(/15\.000,00/).length).toBeGreaterThan(0);
    cleanup();

    presetSession(["odontologo"]);
    stubFetch(async (url, init) => {
      const method = init?.method ?? "GET";
      if (url.includes("/api/caja/cierre") && method === "GET") {
        return jsonResponse(200, cierre());
      }
      if (url.includes("/api/turnos/agenda") && method === "GET") {
        return jsonResponse(200, [TURNO]);
      }
      if (url.includes("/api/pacientes?") && method === "GET") {
        return jsonResponse(200, [PACIENTE]);
      }
      if (
        url.endsWith("/api/pacientes/p-1/cuenta-corriente") &&
        method === "GET"
      ) {
        return jsonResponse(200, {
          paciente_id: "p-1",
          moneda: "ARS",
          saldo: "25000.00",
          movimientos: [DEBITO],
        });
      }
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });
    const odontologoEv = userEvent.setup();
    renderPath("/caja");
    await screen.findByRole("heading", { name: "Caja" });
    await buscarYSeleccionar(odontologoEv);

    expect(
      screen.queryByRole("button", { name: "Registrar cobro" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/tu rol no registra cobros/i)).toBeInTheDocument();
  });
});
