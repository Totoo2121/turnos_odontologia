/** C-15: counter cash API client with fetch mocked. Datos ficticios. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AUTH_STORAGE_KEY } from "../../shared/storage";
import {
  descargarRecibo,
  getCierre,
  getCuenta,
  listTurnosDia,
  parseMedioPago,
  registrarPago,
} from "./caja-api";

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

describe("caja-api (C-15)", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
    localStorage.setItem(
      AUTH_STORAGE_KEY,
      JSON.stringify({ accessToken: "access-caja" }),
    );
  });

  it("lee la cuenta corriente autenticada del paciente", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(200, {
        paciente_id: "p-1",
        moneda: "ARS",
        saldo: "15000.00",
        movimientos: [],
      }),
    );
    vi.stubGlobal("fetch", fetchImpl);

    const cuenta = await getCuenta("p-1");

    expect(cuenta.saldo).toBe("15000.00");
    const [url, init] = calls(fetchImpl)[0];
    expect(String(url)).toContain("/api/pacientes/p-1/cuenta-corriente");
    expect(new Headers(init?.headers).get("authorization")).toBe(
      "Bearer access-caja",
    );
  });

  it("registra un pago con monto, medio y clave de idempotencia", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(201, {
        movimiento: { id: "mov-1", tipo: "credito", monto: "15000.00" },
        saldo: "0.00",
        medio: "efectivo",
        referencia: "pago:efectivo:clave-1",
      }),
    );
    vi.stubGlobal("fetch", fetchImpl);

    const pago = await registrarPago("p-1", {
      monto: 15000,
      medio: "efectivo",
      idempotency_key: "clave-1",
      descripcion: "Saldo ficticio",
    });

    expect(pago.saldo).toBe("0.00");
    const [url, init] = calls(fetchImpl)[0];
    expect(String(url)).toContain("/api/pacientes/p-1/cuenta-corriente/pagos");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      monto: 15000,
      medio: "efectivo",
      idempotency_key: "clave-1",
      descripcion: "Saldo ficticio",
    });
  });

  it("descarga el recibo PDF autenticado", async () => {
    const fetchImpl = vi.fn(
      async () =>
        new Response("recibo-ficticio", {
          status: 200,
          headers: { "content-type": "application/pdf" },
        }),
    );
    vi.stubGlobal("fetch", fetchImpl);

    const blob = await descargarRecibo("mov-1");

    expect(blob.type).toBe("application/pdf");
    const [url, init] = calls(fetchImpl)[0];
    expect(String(url)).toContain("/api/movimientos-cc/mov-1/recibo");
    expect(new Headers(init?.headers).get("authorization")).toBe(
      "Bearer access-caja",
    );
  });

  it("pide el cierre del día con la fecha codificada", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(200, {
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
      }),
    );
    vi.stubGlobal("fetch", fetchImpl);

    const cierre = await getCierre("2030-01-10");

    expect(cierre.cantidad_pagos).toBe(0);
    expect(String(calls(fetchImpl)[0][0])).toContain(
      "/api/caja/cierre?fecha=2030-01-10",
    );
  });

  it("lista los turnos del día con su estado de cobro", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(200, [
        {
          id: "t-1",
          inicio: "2030-01-10T12:00:00Z",
          fin: "2030-01-10T12:30:00Z",
          estado: "pendiente",
          paciente_id: "p-1",
          profesional_id: "prof-1",
          sillon_id: "sil-1",
          cobro: "acreditado",
          cobro_monto: 5000,
        },
      ]),
    );
    vi.stubGlobal("fetch", fetchImpl);

    const turnos = await listTurnosDia("2030-01-10");

    expect(turnos[0].cobro).toBe("acreditado");
    expect(String(calls(fetchImpl)[0][0])).toContain(
      "/api/turnos/agenda?fecha=2030-01-10",
    );
  });

  it("reconoce el medio de pago sólo en referencias de pago", () => {
    expect(parseMedioPago("pago:efectivo:clave-1")).toBe("efectivo");
    expect(parseMedioPago("pago:mp:clave-2")).toBe("mp");
    expect(parseMedioPago("presupuesto:pr-1")).toBeNull();
    expect(parseMedioPago("pago:bitcoin:clave-3")).toBeNull();
    expect(parseMedioPago(null)).toBeNull();
  });
});
