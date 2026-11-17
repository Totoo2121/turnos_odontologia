/** C-15 counter cash API: balances, manual payments, receipts and daily close.
 * Shapes mirror `app/api/caja.py` (snake_case) — no migration involved.
 */
import { ApiClient } from "../../shared/api-client";

const client = new ApiClient();

export type MedioPago = "efectivo" | "transferencia" | "mp";

export const MEDIOS_PAGO: { value: MedioPago; label: string }[] = [
  { value: "efectivo", label: "Efectivo" },
  { value: "transferencia", label: "Transferencia" },
  { value: "mp", label: "Mercado Pago" },
];

export function medioLabel(medio: string): string {
  return MEDIOS_PAGO.find((item) => item.value === medio)?.label ?? medio;
}

export interface MovimientoCC {
  id: string;
  tipo: string;
  monto: string;
  descripcion: string;
  referencia: string | null;
  plan_tratamiento_id?: string | null;
  ocurrido_at?: string | null;
  created_at?: string | null;
}

export interface CuentaCorriente {
  paciente_id: string;
  moneda: string;
  saldo: string;
  movimientos: MovimientoCC[];
}

export interface PagoInput {
  monto: number;
  medio: MedioPago;
  idempotency_key: string;
  descripcion?: string | null;
}

export interface PagoRead {
  movimiento: MovimientoCC;
  saldo: string;
  medio: string;
  referencia: string;
}

export interface TurnoCierre {
  id: string;
  inicio: string;
  fin: string;
  estado: string;
  paciente_id: string | null;
  profesional_id: string | null;
  sillon_id: string | null;
}

export interface CierreCaja {
  fecha: string;
  moneda: string;
  cobrado_total: string;
  por_medio: Record<string, string>;
  cantidad_pagos: number;
  deuda_generada: string;
  diferencia_caja: string;
  turnos_atendidos: number;
  movimientos: MovimientoCC[];
  turnos: TurnoCierre[];
}

/** Agenda read model: adds the Mercado Pago collection state per appointment. */
export interface TurnoCaja {
  id: string;
  inicio: string;
  fin: string;
  estado: string;
  paciente_id: string | null;
  profesional_id: string;
  sillon_id: string;
  cobro: string;
  cobro_monto: number | null;
}

/** Payment reference is `pago:{medio}:{clave}` (backend owns the format). */
export function parseMedioPago(referencia: string | null): MedioPago | null {
  if (referencia === null) {
    return null;
  }
  const [prefix, medio] = referencia.split(":", 2);
  if (prefix !== "pago") {
    return null;
  }
  return MEDIOS_PAGO.some((item) => item.value === medio)
    ? (medio as MedioPago)
    : null;
}

/** One key per attempt; retries reuse it until the server confirms the credit. */
export function nuevaClaveIdempotencia(): string {
  const cryptoApi = globalThis.crypto as Crypto | undefined;
  if (typeof cryptoApi?.randomUUID === "function") {
    return cryptoApi.randomUUID();
  }
  return `pago-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export async function getCuenta(pacienteId: string): Promise<CuentaCorriente> {
  return client.get(`/api/pacientes/${pacienteId}/cuenta-corriente`);
}

export async function registrarPago(
  pacienteId: string,
  input: PagoInput,
): Promise<PagoRead> {
  return client.post(`/api/pacientes/${pacienteId}/cuenta-corriente/pagos`, input);
}

export async function descargarRecibo(movimientoId: string): Promise<Blob> {
  return client.download(`/api/movimientos-cc/${movimientoId}/recibo`);
}

export async function getCierre(fecha: string): Promise<CierreCaja> {
  return client.get(`/api/caja/cierre?fecha=${encodeURIComponent(fecha)}`);
}

export async function listTurnosDia(fecha: string): Promise<TurnoCaja[]> {
  return client.get(`/api/turnos/agenda?fecha=${encodeURIComponent(fecha)}`);
}
