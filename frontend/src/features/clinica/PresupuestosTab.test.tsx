/** C-15 task 4.7: budget builder, lifecycle and consent gate. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PresupuestosTab } from "./PresupuestosTab";
import {
  callsFor,
  jsonResponse,
  seedSession,
  stubFetch,
} from "./clinica-test-utils";

const PRESTACIONES = [
  {
    id: "prest-1",
    nombre: "Limpieza ficticia",
    duracion_min: 30,
    buffer_min: 0,
    precio: "10000.00",
    requiere_consentimiento: false,
    intervalo_control_dias: null,
    is_active: true,
  },
  {
    id: "prest-2",
    nombre: "Obturación ficticia",
    duracion_min: 45,
    buffer_min: 10,
    precio: "15000.00",
    requiere_consentimiento: true,
    intervalo_control_dias: 180,
    is_active: true,
  },
];

const ITEMS = [
  {
    id: "i-1",
    presupuesto_id: "pr-1",
    prestacion_id: "prest-1",
    descripcion: "Limpieza ficticia",
    cantidad: 1,
    precio_unitario: "10000.00",
    importe: "10000.00",
    etapa: 1,
    requiere_consentimiento: false,
    pieza_fdi: null,
    superficie: null,
  },
  {
    id: "i-2",
    presupuesto_id: "pr-1",
    prestacion_id: "prest-2",
    descripcion: "Obturación ficticia",
    cantidad: 1,
    precio_unitario: "15000.00",
    importe: "15000.00",
    etapa: 1,
    requiere_consentimiento: true,
    pieza_fdi: 16,
    superficie: "oclusal",
  },
];

function presupuesto(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "pr-1",
    paciente_id: "p-1",
    historia_clinica_id: "h-1",
    estado: "enviado",
    moneda: "ARS",
    total: "25000.00",
    validez_hasta: null,
    observaciones: null,
    created_at: "2030-01-10T10:00:00Z",
    items: ITEMS,
    ...overrides,
  };
}

function plan(): Record<string, unknown> {
  return {
    id: "plan-1",
    presupuesto_id: "pr-1",
    paciente_id: "p-1",
    consentimiento_id: "c-1",
    estado: "activo",
    total: "25000.00",
    etapas: 1,
    etapa_actual: 1,
    detalle: [{ etapa: 1, subtotal: "25000.00", items: ITEMS }],
  };
}

describe("PresupuestosTab (C-15 4.7)", () => {
  beforeEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
    seedSession();
  });

  it("arma un presupuesto con dos ítems y muestra el total del servidor", async () => {
    const fetchImpl = stubFetch((url, init) => {
      const method = init?.method ?? "GET";
      if (url.includes("/api/presupuestos?") && method === "GET") {
        return jsonResponse(200, []);
      }
      if (url.endsWith("/api/prestaciones") && method === "GET") {
        return jsonResponse(200, PRESTACIONES);
      }
      if (url.endsWith("/api/presupuestos") && method === "POST") {
        return jsonResponse(
          201,
          presupuesto({ id: "pr-nuevo", estado: "borrador" }),
        );
      }
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });

    render(
      <PresupuestosTab pacienteId="p-1" historiaId="h-1" canWrite />,
    );
    const userEv = userEvent.setup();
    await screen.findByText("Todavía no hay presupuestos.");

    await userEv.selectOptions(
      screen.getByLabelText("Prestación"),
      "prest-1",
    );
    await userEv.click(screen.getByRole("button", { name: "Agregar ítem" }));

    await userEv.selectOptions(
      screen.getByLabelText("Prestación"),
      "prest-2",
    );
    await userEv.type(screen.getByLabelText("Pieza FDI (opcional)"), "16");
    await userEv.selectOptions(
      screen.getByLabelText("Superficie (opcional)"),
      "oclusal",
    );
    await userEv.click(screen.getByRole("button", { name: "Agregar ítem" }));
    await userEv.click(
      screen.getByRole("button", { name: "Guardar presupuesto" }),
    );

    await waitFor(() => {
      expect(screen.getAllByText(/25\.000,00/).length).toBeGreaterThan(0);
    });
    const [, init] = callsFor(fetchImpl, "POST")[0];
    const body = JSON.parse(String(init?.body)) as {
      paciente_id: string;
      historia_clinica_id: string;
      items: { prestacion_id: string; pieza_fdi?: number | null }[];
    };
    expect(body.paciente_id).toBe("p-1");
    expect(body.historia_clinica_id).toBe("h-1");
    expect(body.items).toHaveLength(2);
    expect(body.items[1]).toMatchObject({
      prestacion_id: "prest-2",
      pieza_fdi: 16,
      superficie: "oclusal",
    });
  });

  it("acepta con consentimiento y muestra el plan y la deuda", async () => {
    stubFetch((url, init) => {
      const method = init?.method ?? "GET";
      if (url.includes("/api/presupuestos?") && method === "GET") {
        return jsonResponse(200, [presupuesto()]);
      }
      if (url.endsWith("/api/prestaciones") && method === "GET") {
        return jsonResponse(200, PRESTACIONES);
      }
      if (url.endsWith("/api/presupuestos/pr-1/aceptar") && method === "POST") {
        return jsonResponse(
          200,
          presupuesto({
            estado: "aceptado",
            plan_id: "plan-1",
            movimiento_id: "mov-1",
          }),
        );
      }
      if (url.endsWith("/api/planes-tratamiento/plan-1") && method === "GET") {
        return jsonResponse(200, plan());
      }
      if (url.endsWith("/api/pacientes/p-1/cuenta-corriente") && method === "GET") {
        return jsonResponse(200, {
          paciente_id: "p-1",
          moneda: "ARS",
          saldo: "0.00",
          movimientos: [],
        });
      }
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });

    render(
      <PresupuestosTab pacienteId="p-1" historiaId="h-1" canWrite />,
    );
    const userEv = userEvent.setup();
    await screen.findByRole("button", { name: "Aceptar presupuesto" });

    await userEv.click(
      screen.getByRole("button", { name: "Aceptar presupuesto" }),
    );

    expect(
      await screen.findByText("Plan de tratamiento generado"),
    ).toBeInTheDocument();
    expect(screen.getByText(/La deuda quedó registrada/)).toBeInTheDocument();
    expect(screen.getByText(/Saldo: \$\s*0,00/)).toBeInTheDocument();
  });

  it("traduce el 409 consentimiento_requerido y conserva el estado enviado", async () => {
    stubFetch((url, init) => {
      const method = init?.method ?? "GET";
      if (url.includes("/api/presupuestos?") && method === "GET") {
        return jsonResponse(200, [presupuesto()]);
      }
      if (url.endsWith("/api/prestaciones") && method === "GET") {
        return jsonResponse(200, PRESTACIONES);
      }
      if (url.endsWith("/api/presupuestos/pr-1/aceptar") && method === "POST") {
        return jsonResponse(409, { detail: "consentimiento_requerido" });
      }
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });

    render(
      <PresupuestosTab pacienteId="p-1" historiaId="h-1" canWrite />,
    );
    const userEv = userEvent.setup();
    await screen.findByRole("button", { name: "Aceptar presupuesto" });

    await userEv.click(
      screen.getByRole("button", { name: "Aceptar presupuesto" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "El presupuesto requiere un consentimiento invasivo firmado.",
    );
    expect(screen.getByText("Enviado")).toBeInTheDocument();
    expect(screen.getByText(/25\.000,00/)).toBeInTheDocument();
  });

  it("recepción ve los presupuestos sin acciones de escritura", async () => {
    stubFetch((url, init) => {
      const method = init?.method ?? "GET";
      if (url.includes("/api/presupuestos?") && method === "GET") {
        return jsonResponse(200, [presupuesto()]);
      }
      if (url.endsWith("/api/prestaciones") && method === "GET") {
        return jsonResponse(200, PRESTACIONES);
      }
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });

    render(
      <PresupuestosTab
        pacienteId="p-1"
        historiaId="h-1"
        canWrite={false}
      />,
    );

    expect(await screen.findByText(/25\.000,00/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Guardar presupuesto" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Aceptar presupuesto" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Enviar presupuesto" }),
    ).not.toBeInTheDocument();
  });
});
