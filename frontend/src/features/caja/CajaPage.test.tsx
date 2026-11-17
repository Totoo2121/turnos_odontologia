/** C-15 tasks 5.1–5.3: counter cash UI. Datos ficticios. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useAuthStore, type Role } from "../auth/auth-store";
import {
  callsFor,
  jsonResponse,
  pdfResponse,
  seedSession,
  stubFetch,
} from "../clinica/clinica-test-utils";
import { CajaPage } from "./CajaPage";

const PACIENTE = {
  id: "p-1",
  tenant_id: "t-ficticio-1",
  nombre: "Pérez Ficticio",
  telefono: "555-0000",
  dni: "DNI-000",
  email: null,
  obra_social: null,
  consentimiento_datos: true,
  is_active: true,
  created_at: "2030-01-01T10:00:00Z",
};

const DEBITO = {
  id: "mov-1",
  tipo: "debito",
  monto: "25000.00",
  descripcion: "Presupuesto aceptado",
  referencia: "presupuesto:pr-1",
  ocurrido_at: "2030-01-10T10:00:00Z",
};

const CREDITO = {
  id: "mov-2",
  tipo: "credito",
  monto: "10000.00",
  descripcion: "Cobro anterior",
  referencia: "pago:efectivo:clave-vieja",
  ocurrido_at: "2030-01-10T11:00:00Z",
};

function cuenta(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    paciente_id: "p-1",
    moneda: "ARS",
    saldo: "15000.00",
    movimientos: [DEBITO, CREDITO],
    ...overrides,
  };
}

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

function cierreConDatos(): Record<string, unknown> {
  return {
    fecha: "2030-01-10",
    moneda: "ARS",
    cobrado_total: "30000.00",
    por_medio: {
      efectivo: "15000.00",
      transferencia: "10000.00",
      mp: "5000.00",
    },
    cantidad_pagos: 3,
    deuda_generada: "40000.00",
    diferencia_caja: "-10000.00",
    turnos_atendidos: 3,
    movimientos: [CREDITO],
    turnos: [],
  };
}

const TURNO_ACREDITADO = {
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

const TURNO_SIN_SENA = {
  id: "t-2",
  inicio: "2030-01-10T13:00:00Z",
  fin: "2030-01-10T13:30:00Z",
  estado: "pendiente",
  paciente_id: null,
  profesional_id: "prof-1",
  sillon_id: "sil-1",
  cobro: "sin-sena",
  cobro_monto: null,
};

type ExtraHandler = (
  url: string,
  init?: RequestInit,
) => Response | null | Promise<Response | null>;

function stubCaja(extra: ExtraHandler = () => null): ReturnType<typeof vi.fn> {
  return stubFetch(async (url, init) => {
    const method = init?.method ?? "GET";
    const custom = await extra(url, init);
    if (custom !== null) {
      return custom;
    }
    if (url.includes("/api/caja/cierre") && method === "GET") {
      return jsonResponse(200, cierreVacio());
    }
    if (url.includes("/api/turnos/agenda") && method === "GET") {
      return jsonResponse(200, []);
    }
    throw new Error(`unexpected fetch: ${method} ${url}`);
  });
}

function presetSession(roles: Role[]): void {
  seedSession();
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

async function abrirCuenta(
  userEv: ReturnType<typeof userEvent.setup>,
): Promise<void> {
  await userEv.type(screen.getByRole("searchbox"), "Pérez");
  await userEv.click(screen.getByRole("button", { name: "Buscar" }));
  await screen.findByText("Pérez Ficticio");
  await userEv.click(screen.getByRole("button", { name: "Ver cuenta" }));
  await screen.findByText("Cuenta corriente de Pérez Ficticio");
}

describe("CajaPage (C-15 5.1–5.3)", () => {
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

  it("muestra saldo, movimientos y referencia del paciente con deuda", async () => {
    presetSession(["recepcion"]);
    stubCaja((url, init) => {
      const method = init?.method ?? "GET";
      if (url.includes("/api/pacientes?") && method === "GET") {
        return jsonResponse(200, [PACIENTE]);
      }
      if (url.endsWith("/api/pacientes/p-1/cuenta-corriente") && method === "GET") {
        return jsonResponse(200, cuenta());
      }
      return null;
    });
    const userEv = userEvent.setup();

    render(<CajaPage />);
    await abrirCuenta(userEv);

    const region = screen.getByRole("region", {
      name: "Cuenta corriente de Pérez Ficticio",
    });
    expect(within(region).getByText(/15\.000,00/)).toBeInTheDocument();
    expect(within(region).getByText("Presupuesto aceptado")).toBeInTheDocument();
    expect(within(region).getByText(/presupuesto:pr-1/)).toBeInTheDocument();
    expect(
      within(region).getByRole("button", { name: "Descargar recibo" }),
    ).toBeInTheDocument();
  });

  it("muestra saldo 0 y estado vacío para un paciente sin cuenta", async () => {
    presetSession(["recepcion"]);
    stubCaja((url, init) => {
      const method = init?.method ?? "GET";
      if (url.includes("/api/pacientes?") && method === "GET") {
        return jsonResponse(200, [PACIENTE]);
      }
      if (url.endsWith("/api/pacientes/p-1/cuenta-corriente") && method === "GET") {
        return jsonResponse(
          200,
          cuenta({ saldo: "0.00", movimientos: [] }),
        );
      }
      return null;
    });
    const userEv = userEvent.setup();

    render(<CajaPage />);
    await abrirCuenta(userEv);

    const region = screen.getByRole("region", {
      name: "Cuenta corriente de Pérez Ficticio",
    });
    expect(within(region).getByText(/0,00/)).toBeInTheDocument();
    expect(
      within(region).getByText(
        "El paciente no tiene movimientos en su cuenta corriente.",
      ),
    ).toBeInTheDocument();
  });

  it("cobra en efectivo, actualiza el saldo desde la respuesta y registra el pago", async () => {
    presetSession(["recepcion"]);
    const fetchImpl = stubCaja((url, init) => {
      const method = init?.method ?? "GET";
      if (url.includes("/api/pacientes?") && method === "GET") {
        return jsonResponse(200, [PACIENTE]);
      }
      if (url.endsWith("/api/pacientes/p-1/cuenta-corriente") && method === "GET") {
        return jsonResponse(200, cuenta());
      }
      if (
        url.endsWith("/api/pacientes/p-1/cuenta-corriente/pagos") &&
        method === "POST"
      ) {
        return jsonResponse(201, {
          movimiento: {
            id: "mov-pago",
            tipo: "credito",
            monto: "15000.00",
            descripcion: "Cobro en Efectivo",
            referencia: "pago:efectivo:clave-nueva",
            ocurrido_at: "2030-01-10T12:00:00Z",
          },
          saldo: "0.00",
          medio: "efectivo",
          referencia: "pago:efectivo:clave-nueva",
        });
      }
      return null;
    });
    const userEv = userEvent.setup();

    render(<CajaPage />);
    await abrirCuenta(userEv);
    await userEv.type(screen.getByLabelText("Monto"), "15000");
    await userEv.click(screen.getByRole("button", { name: "Registrar cobro" }));

    expect(
      await screen.findByText(/Cobro registrado con Efectivo/),
    ).toBeInTheDocument();
    const region = screen.getByRole("region", {
      name: "Cuenta corriente de Pérez Ficticio",
    });
    expect(within(region).getAllByText(/0,00/).length).toBeGreaterThan(0);
    expect(within(region).getByText("Cobro en Efectivo")).toBeInTheDocument();
    const [, init] = callsFor(fetchImpl, "POST")[0];
    const body = JSON.parse(String(init?.body)) as {
      monto: number;
      medio: string;
      idempotency_key: string;
    };
    expect(body.monto).toBe(15000);
    expect(body.medio).toBe("efectivo");
    expect(body.idempotency_key.length).toBeGreaterThan(0);
  });

  it("rechaza un monto cero sin llamar a la API", async () => {
    presetSession(["recepcion"]);
    const fetchImpl = stubCaja((url, init) => {
      const method = init?.method ?? "GET";
      if (url.includes("/api/pacientes?") && method === "GET") {
        return jsonResponse(200, [PACIENTE]);
      }
      if (url.endsWith("/api/pacientes/p-1/cuenta-corriente") && method === "GET") {
        return jsonResponse(200, cuenta());
      }
      return null;
    });
    const userEv = userEvent.setup();

    render(<CajaPage />);
    await abrirCuenta(userEv);
    await userEv.type(screen.getByLabelText("Monto"), "0");
    await userEv.click(screen.getByRole("button", { name: "Registrar cobro" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "El monto debe ser mayor a cero.",
    );
    expect(callsFor(fetchImpl, "POST")).toHaveLength(0);
  });

  it("reintenta con la misma clave de idempotencia sin duplicar el crédito", async () => {
    presetSession(["recepcion"]);
    let intentos = 0;
    const fetchImpl = stubCaja((url, init) => {
      const method = init?.method ?? "GET";
      if (url.includes("/api/pacientes?") && method === "GET") {
        return jsonResponse(200, [PACIENTE]);
      }
      if (url.endsWith("/api/pacientes/p-1/cuenta-corriente") && method === "GET") {
        return jsonResponse(200, cuenta());
      }
      if (
        url.endsWith("/api/pacientes/p-1/cuenta-corriente/pagos") &&
        method === "POST"
      ) {
        intentos += 1;
        if (intentos === 1) {
          return jsonResponse(500, { detail: "fallo temporal" });
        }
        return jsonResponse(201, {
          movimiento: {
            id: "mov-reintento",
            tipo: "credito",
            monto: "15000.00",
            descripcion: "Cobro reintentado",
            referencia: "pago:efectivo:clave-reintento",
            ocurrido_at: "2030-01-10T12:00:00Z",
          },
          saldo: "0.00",
          medio: "efectivo",
          referencia: "pago:efectivo:clave-reintento",
        });
      }
      return null;
    });
    const userEv = userEvent.setup();

    render(<CajaPage />);
    await abrirCuenta(userEv);
    await userEv.type(screen.getByLabelText("Monto"), "15000");
    await userEv.click(screen.getByRole("button", { name: "Registrar cobro" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("fallo temporal");

    await userEv.click(screen.getByRole("button", { name: "Registrar cobro" }));
    expect(
      await screen.findByText(/Cobro registrado con Efectivo/),
    ).toBeInTheDocument();

    const posts = callsFor(fetchImpl, "POST");
    expect(posts).toHaveLength(2);
    const first = JSON.parse(String(posts[0][1]?.body)) as {
      idempotency_key: string;
    };
    const second = JSON.parse(String(posts[1][1]?.body)) as {
      idempotency_key: string;
    };
    expect(first.idempotency_key).toBe(second.idempotency_key);
  });

  it("cobra por Mercado Pago y descarga el recibo autenticado", async () => {
    presetSession(["recepcion"]);
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

    const fetchImpl = stubCaja((url, init) => {
      const method = init?.method ?? "GET";
      if (url.includes("/api/pacientes?") && method === "GET") {
        return jsonResponse(200, [PACIENTE]);
      }
      if (url.endsWith("/api/pacientes/p-1/cuenta-corriente") && method === "GET") {
        return jsonResponse(
          200,
          cuenta({ saldo: "25000.00", movimientos: [DEBITO] }),
        );
      }
      if (
        url.endsWith("/api/pacientes/p-1/cuenta-corriente/pagos") &&
        method === "POST"
      ) {
        return jsonResponse(201, {
          movimiento: {
            id: "mov-mp",
            tipo: "credito",
            monto: "25000.00",
            descripcion: "Cobro en Mercado Pago",
            referencia: "pago:mp:clave-mp",
            ocurrido_at: "2030-01-10T12:00:00Z",
          },
          saldo: "0.00",
          medio: "mp",
          referencia: "pago:mp:clave-mp",
        });
      }
      if (
        url.endsWith("/api/movimientos-cc/mov-mp/recibo") &&
        method === "GET"
      ) {
        return pdfResponse();
      }
      return null;
    });
    const userEv = userEvent.setup();

    render(<CajaPage />);
    await abrirCuenta(userEv);
    await userEv.selectOptions(screen.getByLabelText("Medio de pago"), "mp");
    await userEv.type(screen.getByLabelText("Monto"), "25000");
    await userEv.click(screen.getByRole("button", { name: "Registrar cobro" }));

    expect(
      await screen.findByText(/Cobro registrado con Mercado Pago/),
    ).toBeInTheDocument();
    const [, postInit] = callsFor(fetchImpl, "POST")[0];
    expect(
      (JSON.parse(String(postInit?.body)) as { medio: string }).medio,
    ).toBe("mp");

    await userEv.click(
      screen.getByRole("button", { name: "Descargar recibo" }),
    );
    await waitFor(() => {
      expect(createObjectURL).toHaveBeenCalledTimes(1);
    });
    const blob = createObjectURL.mock.calls[0][0] as Blob;
    expect(blob.type).toBe("application/pdf");
  });

  it("odontólogo consulta la caja pero no ve el formulario de cobro", async () => {
    presetSession(["odontologo"]);
    stubCaja((url, init) => {
      const method = init?.method ?? "GET";
      if (url.includes("/api/pacientes?") && method === "GET") {
        return jsonResponse(200, [PACIENTE]);
      }
      if (url.endsWith("/api/pacientes/p-1/cuenta-corriente") && method === "GET") {
        return jsonResponse(200, cuenta());
      }
      return null;
    });
    const userEv = userEvent.setup();

    render(<CajaPage />);
    await abrirCuenta(userEv);

    expect(
      screen.queryByRole("button", { name: "Registrar cobro" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/tu rol no registra cobros/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Cierre de caja")).toBeInTheDocument();
  });

  it("muestra el cierre con totales por medio, deuda, diferencia y turnos", async () => {
    presetSession(["recepcion"]);
    stubCaja((url, init) => {
      const method = init?.method ?? "GET";
      if (url.includes("/api/caja/cierre") && method === "GET") {
        return jsonResponse(200, cierreConDatos());
      }
      if (url.includes("/api/turnos/agenda") && method === "GET") {
        return jsonResponse(200, [TURNO_ACREDITADO, TURNO_SIN_SENA]);
      }
      if (url.includes("/api/pacientes?") && method === "GET") {
        return jsonResponse(200, [PACIENTE]);
      }
      if (url.endsWith("/api/pacientes/p-1/cuenta-corriente") && method === "GET") {
        return jsonResponse(200, cuenta());
      }
      if (url.endsWith("/api/pacientes/p-1") && method === "GET") {
        return jsonResponse(200, PACIENTE);
      }
      return null;
    });
    const userEv = userEvent.setup();

    render(<CajaPage />);

    expect(await screen.findByText("Diferencia de caja")).toBeInTheDocument();
    expect(screen.getByText("Cobrado por medio")).toBeInTheDocument();
    expect(screen.getAllByText(/30\.000,00/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/40\.000,00/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/10\.000,00/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Acreditado/)).toBeInTheDocument();
    expect(screen.getByText(/Sin seña/)).toBeInTheDocument();
    expect(screen.getAllByText(/5\.000,00/).length).toBeGreaterThan(0);

    await userEv.click(
      screen.getByRole("button", { name: "Ver cuenta del turno" }),
    );
    expect(
      await screen.findByText("Cuenta corriente de Pérez Ficticio"),
    ).toBeInTheDocument();
  });

  it("día sin movimientos muestra totales en cero y estados vacíos", async () => {
    presetSession(["recepcion"]);
    stubCaja();

    render(<CajaPage />);

    expect(
      await screen.findByText("No hay movimientos registrados para la fecha."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No hay turnos agendados para la fecha."),
    ).toBeInTheDocument();
    const region = screen.getByRole("region", { name: "Cierre de caja" });
    expect(within(region).getAllByText(/0,00/).length).toBeGreaterThan(3);
  });
});
