import { ApiClient } from "../../shared/api-client";

const client = new ApiClient();

export interface CrearTurnoPayload {
  profesionalId: string;
  sillonId: string;
  inicio: string;
  prestacionId: string;
  pacienteId: string;
  origen?: "recepcion" | "control" | "mostrador";
}

export async function fetchAgenda(fecha: string, vista: "dia" | "semana" = "dia"): Promise<any[]> {
  return client.get(`/api/turnos/agenda?fecha=${encodeURIComponent(fecha)}&vista=${vista}`);
}

export async function crearTurno(payload: CrearTurnoPayload): Promise<any> {
  return client.post("/api/turnos", {
    paciente_id: payload.pacienteId,
    profesional_id: payload.profesionalId,
    sillon_id: payload.sillonId,
    prestacion_id: payload.prestacionId,
    inicio: payload.inicio,
    origen: payload.origen ?? "recepcion",
  });
}

export async function cambiarEstado(id: string, estado: string): Promise<any> {
  return client.patch(`/api/turnos/${id}/estado`, { estado });
}

export async function cancelarTurno(id: string): Promise<any> {
  return client.post(`/api/turnos/${id}/cancelar`);
}

// Reprogramar/sobreturno siguen siendo deuda de C-06: no hay endpoint montado.
