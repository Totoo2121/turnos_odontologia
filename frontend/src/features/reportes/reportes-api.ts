import { ApiClient } from "../../shared/api-client";

const client = new ApiClient();

export interface FilaOcupacion {
  profesional_id: string;
  profesional: string;
  turnos: number;
  minutos_ocupados: number;
  atendidos: number;
  ausentes: number;
  cancelados: number;
}

export interface FilaAusentismo {
  profesional_id: string;
  profesional: string;
  turnos: number;
  ausentes: number;
  cancelados: number;
  tasa_ausentismo: number;
}

export interface Reporte<T> {
  desde: string;
  hasta: string;
  alcance: "total" | "operativo" | "propio";
  filas: T[];
}

export interface ReporteRecaudacion {
  desde: string;
  hasta: string;
  alcance: "total" | "propio";
  senias_acreditadas: string;
  cobros_cuenta_corriente: string;
  total_cobrado: string;
  cantidad_cobros_cuenta_corriente: number;
  deuda_neta_planes: string;
  por_profesional: Array<{
    profesional_id: string;
    profesional: string;
    senias_acreditadas: string;
    cantidad_senias: number;
  }>;
}

function query(desde: string, hasta: string): string {
  const params = new URLSearchParams({ desde, hasta });
  return params.toString();
}

export const getOcupacion = (desde: string, hasta: string) =>
  client.get<Reporte<FilaOcupacion>>(`/api/reportes/ocupacion?${query(desde, hasta)}`);

export const getAusentismo = (desde: string, hasta: string) =>
  client.get<Reporte<FilaAusentismo>>(`/api/reportes/ausentismo?${query(desde, hasta)}`);

export const getRecaudacion = (desde: string, hasta: string) =>
  client.get<ReporteRecaudacion>(`/api/reportes/recaudacion?${query(desde, hasta)}`);
