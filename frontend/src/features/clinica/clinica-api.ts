/** C-15 clinical API client: patients, HCE, odontogram, attachments,
 * budgets, plans and consentimientos. All shapes mirror the FastAPI schemas
 * (snake_case) so the backend stays the single source of truth.
 */
import { ApiClient, ApiError } from "../../shared/api-client";

const client = new ApiClient();

// --- Types ----------------------------------------------------------------

export interface Paciente {
  id: string;
  tenant_id?: string;
  nombre: string;
  telefono: string;
  dni: string | null;
  email: string | null;
  obra_social: string | null;
  consentimiento_datos: boolean;
  consentimiento_at?: string | null;
  is_active: boolean;
  created_at?: string | null;
}

export type PacienteCreate = Pick<Paciente, "nombre" | "telefono" | "dni" | "email" | "obra_social" | "consentimiento_datos"> & {
  consentimiento_at: string | null;
};

export async function createPaciente(body: PacienteCreate): Promise<Paciente> {
  return client.post<Paciente>("/api/pacientes", body);
}

export interface Historia {
  id: string;
  paciente_id: string;
  alergias: string | null;
  medicacion: string | null;
  antecedentes: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface Evolucion {
  id: string;
  historia_clinica_id: string;
  autor_usuario_id: string;
  autor_profesional_id?: string | null;
  contenido: string;
  corrige_evolucion_id: string | null;
  created_at?: string | null;
}

export type EstadoPieza =
  | "sano"
  | "caries"
  | "obturacion"
  | "corona"
  | "endodoncia"
  | "extraccion"
  | "implante"
  | "sellador";

export type Superficie =
  | "oclusal"
  | "mesial"
  | "distal"
  | "vestibular"
  | "lingual"
  | "palatina"
  | "incisal";

export interface EstadoPiezaActual {
  pieza_fdi: number;
  superficie: Superficie | null;
  estado: EstadoPieza;
  fecha: string;
  evento_id: string;
  autor_usuario_id: string;
  autor_profesional_id?: string | null;
}

export interface Odontograma {
  id: string;
  historia_clinica_id: string;
  estado_actual: EstadoPiezaActual[];
}

export interface EventoPieza {
  id: string;
  odontograma_id: string;
  pieza_fdi: number;
  superficie: Superficie | null;
  estado: EstadoPieza;
  fecha: string;
  autor_usuario_id: string;
  autor_profesional_id?: string | null;
  observaciones?: string | null;
  created_at?: string | null;
}

export interface Adjunto {
  id: string;
  historia_clinica_id: string;
  tipo: string;
  storage_key: string;
  nombre_original: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  origen: string | null;
  subido_por_usuario_id?: string | null;
  created_at?: string | null;
}

export interface PresupuestoItem {
  id: string;
  presupuesto_id: string;
  prestacion_id: string;
  descripcion: string;
  cantidad: number;
  precio_unitario: string;
  importe: string;
  etapa: number;
  requiere_consentimiento: boolean;
  pieza_fdi: number | null;
  superficie: Superficie | null;
}

export interface Presupuesto {
  id: string;
  paciente_id: string;
  historia_clinica_id: string;
  estado: "borrador" | "enviado" | "aceptado" | "rechazado";
  moneda: string;
  total: string;
  validez_hasta: string | null;
  enviado_at?: string | null;
  aceptado_at?: string | null;
  rechazado_at?: string | null;
  observaciones: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  items: PresupuestoItem[];
}

export interface AceptacionPresupuesto extends Presupuesto {
  plan_id: string | null;
  movimiento_id: string | null;
}

export interface PlanEtapa {
  etapa: number;
  subtotal: string;
  items: PresupuestoItem[];
}

export interface PlanTratamiento {
  id: string;
  presupuesto_id: string;
  paciente_id: string;
  consentimiento_id: string | null;
  estado: string;
  total: string;
  etapas: number;
  etapa_actual: number;
  detalle: PlanEtapa[];
}

export interface Consentimiento {
  id: string;
  paciente_id: string;
  historia_clinica_id: string;
  tipo: string;
  texto_version: string;
  texto: string;
  plan_invasivo: boolean;
  firmante_nombre: string;
  firmante_dni: string | null;
  firmado_at: string;
  firma_hash: string;
  hash_valido: boolean;
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

export interface Prestacion {
  id: string;
  nombre: string;
  duracion_min: number;
  buffer_min: number;
  precio: string | null;
  requiere_consentimiento: boolean;
  intervalo_control_dias: number | null;
  is_active: boolean;
}

export interface Profesional {
  id: string;
  nombre: string;
  matricula: string | null;
  especialidades: string[];
  prestacion_ids: string[];
  activo: boolean;
}

export interface Sillon {
  id: string;
  nombre: string;
  activo: boolean;
}

export interface AgendaTurno {
  id: string;
  inicio: string;
  fin: string;
  estado: string;
  profesional_id: string;
  sillon_id: string;
  prestacion_id?: string | null;
  paciente_id: string | null;
  sobreturno: boolean;
  cobro: string;
  cobro_monto: number | null;
}

/** Turno lifecycle read shape (`POST /api/turnos`, `PATCH .../estado`). */
export interface Turno {
  id: string;
  paciente_id: string | null;
  profesional_id: string;
  sillon_id: string;
  prestacion_id: string;
  inicio: string;
  fin: string;
  estado: string;
  origen: string;
  sobreturno: boolean;
  confirmado_at?: string | null;
}

// --- Clinical rules (same table as C-13) ----------------------------------

export const ESTADOS_PIEZA: EstadoPieza[] = [
  "sano",
  "caries",
  "obturacion",
  "corona",
  "endodoncia",
  "extraccion",
  "implante",
  "sellador",
];

export const SUPERFICIES: Superficie[] = [
  "oclusal",
  "mesial",
  "distal",
  "vestibular",
  "lingual",
  "palatina",
  "incisal",
];

export const ESTADOS_CON_SUPERFICIE = new Set<EstadoPieza>([
  "caries",
  "obturacion",
  "sellador",
]);
export const ESTADOS_SIN_SUPERFICIE = new Set<EstadoPieza>([
  "corona",
  "endodoncia",
  "extraccion",
  "implante",
]);

/** Client-side mirror of the backend validation; returns a readable error. */
export function validarEventoPieza(
  estado: EstadoPieza,
  superficie: Superficie | null,
): string | null {
  if (ESTADOS_CON_SUPERFICIE.has(estado) && superficie === null) {
    return `El estado ${estado} requiere una superficie.`;
  }
  if (ESTADOS_SIN_SUPERFICIE.has(estado) && superficie !== null) {
    return `El estado ${estado} no admite superficie.`;
  }
  return null;
}

// --- Errors ---------------------------------------------------------------

/** Maps backend errors to UI copy without leaking tenant/internal details. */
export function mensajeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return "No tenés permiso para esta acción.";
    }
    if (error.status === 404) {
      return "No se encontró el recurso en este tenant.";
    }
    if (error.message === "consentimiento_requerido") {
      return "El presupuesto requiere un consentimiento invasivo firmado.";
    }
    return error.message;
  }
  return "Ocurrió un error inesperado. Reintentá.";
}

export function abrirBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

// --- Pacientes ------------------------------------------------------------

export async function listPacientes(
  q: string,
  limit = 50,
  offset = 0,
): Promise<Paciente[]> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (q.trim().length > 0) {
    params.set("q", q.trim());
  }
  return client.get(`/api/pacientes?${params.toString()}`);
}

export async function getPaciente(id: string): Promise<Paciente> {
  return client.get(`/api/pacientes/${id}`);
}

// --- Historia clínica -----------------------------------------------------

/** Idempotent: the backend returns the existing history or creates one. */
export async function abrirHistoria(pacienteId: string): Promise<Historia> {
  return client.post("/api/historias-clinicas", { paciente_id: pacienteId });
}

export async function actualizarAnamnesis(
  historiaId: string,
  patch: Partial<Pick<Historia, "alergias" | "medicacion" | "antecedentes">>,
): Promise<Historia> {
  return client.patch(`/api/historias-clinicas/${historiaId}`, patch);
}

export async function listEvoluciones(historiaId: string): Promise<Evolucion[]> {
  return client.get(`/api/historias-clinicas/${historiaId}/evoluciones`);
}

export async function crearEvolucion(
  historiaId: string,
  contenido: string,
  corrigeEvolucionId: string | null,
): Promise<Evolucion> {
  return client.post(`/api/historias-clinicas/${historiaId}/evoluciones`, {
    contenido,
    corrige_evolucion_id: corrigeEvolucionId,
  });
}

// --- Odontograma ----------------------------------------------------------

export async function getOdontograma(historiaId: string): Promise<Odontograma> {
  return client.get(`/api/odontogramas/${historiaId}`);
}

export async function crearEventoPieza(
  historiaId: string,
  payload: {
    pieza_fdi: number;
    estado: EstadoPieza;
    superficie: Superficie | null;
    observaciones?: string | null;
  },
): Promise<EventoPieza> {
  return client.post(`/api/odontogramas/${historiaId}/eventos`, payload);
}

// --- Adjuntos -------------------------------------------------------------

export async function listAdjuntos(historiaId: string): Promise<Adjunto[]> {
  return client.get(`/api/historias-clinicas/${historiaId}/adjuntos`);
}

export async function subirAdjunto(
  historiaId: string,
  input: { tipo: string; archivo: File; origen: string | null },
): Promise<Adjunto> {
  const form = new FormData();
  form.append("tipo", input.tipo);
  form.append("archivo", input.archivo);
  if (input.origen !== null && input.origen.trim().length > 0) {
    form.append("origen", input.origen.trim());
  }
  return client.upload(`/api/historias-clinicas/${historiaId}/adjuntos`, form);
}

export async function urlAdjunto(
  adjuntoId: string,
): Promise<{ url: string; expires_at: string }> {
  return client.get(`/api/adjuntos/${adjuntoId}/url`);
}

// --- Presupuestos y planes ------------------------------------------------

export interface ItemPresupuestoInput {
  prestacion_id: string;
  cantidad: number;
  etapa: number;
  pieza_fdi?: number | null;
  superficie?: Superficie | null;
}

export async function listPresupuestos(
  pacienteId: string,
): Promise<Presupuesto[]> {
  return client.get(
    `/api/presupuestos?paciente_id=${encodeURIComponent(pacienteId)}`,
  );
}

export async function crearPresupuesto(input: {
  paciente_id: string;
  historia_clinica_id: string;
  observaciones: string | null;
  items: ItemPresupuestoInput[];
}): Promise<Presupuesto> {
  return client.post("/api/presupuestos", input);
}

export async function enviarPresupuesto(
  presupuestoId: string,
): Promise<Presupuesto> {
  return client.post(`/api/presupuestos/${presupuestoId}/enviar`);
}

export async function aceptarPresupuesto(
  presupuestoId: string,
): Promise<AceptacionPresupuesto> {
  return client.post(`/api/presupuestos/${presupuestoId}/aceptar`);
}

export async function rechazarPresupuesto(
  presupuestoId: string,
): Promise<Presupuesto> {
  return client.post(`/api/presupuestos/${presupuestoId}/rechazar`);
}

export async function getPlan(planId: string): Promise<PlanTratamiento> {
  return client.get(`/api/planes-tratamiento/${planId}`);
}

// --- Consentimientos ------------------------------------------------------

export async function listConsentimientos(
  pacienteId: string,
): Promise<Consentimiento[]> {
  return client.get(`/api/pacientes/${pacienteId}/consentimientos`);
}

export interface ConsentimientoInput {
  historia_clinica_id: string;
  tipo: string;
  texto: string;
  texto_version: string;
  firmante_nombre: string;
  firmante_dni: string | null;
  plan_invasivo: boolean;
}

export async function crearConsentimiento(
  input: ConsentimientoInput,
): Promise<Consentimiento> {
  return client.post("/api/consentimientos", input);
}

export async function descargarConsentimientoPdf(
  consentimientoId: string,
): Promise<Blob> {
  return client.download(`/api/consentimientos/${consentimientoId}/pdf`);
}

// --- Turnos del paciente y catálogo --------------------------------------

export async function listTurnosDia(fecha: string): Promise<AgendaTurno[]> {
  return client.get(`/api/turnos/agenda?fecha=${encodeURIComponent(fecha)}`);
}

export async function cambiarEstadoTurno(
  turnoId: string,
  estado: string,
): Promise<Turno> {
  return client.patch(`/api/turnos/${turnoId}/estado`, { estado });
}

export async function crearTurnoControl(input: {
  paciente_id: string;
  profesional_id: string;
  sillon_id: string;
  prestacion_id: string;
  inicio: string;
}): Promise<Turno> {
  return client.post("/api/turnos", {
    ...input,
    origen: "control",
  });
}

export async function listPrestaciones(): Promise<Prestacion[]> {
  return client.get("/api/prestaciones");
}

export async function listProfesionales(): Promise<Profesional[]> {
  return client.get("/api/profesionales");
}

export async function listSillones(): Promise<Sillon[]> {
  return client.get("/api/sillones");
}

export async function getCuentaCorriente(
  pacienteId: string,
): Promise<CuentaCorriente> {
  return client.get(`/api/pacientes/${pacienteId}/cuenta-corriente`);
}
