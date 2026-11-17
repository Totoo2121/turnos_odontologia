import { ApiClient } from "../shared/api-client";

const client = new ApiClient();

export interface AdminPerfil {
  id: string;
  nombre: string;
  slug_reserva: string;
  moneda: string;
}

export interface AdminUsuario {
  id: string;
  email: string;
  nombre: string | null;
  rol: string;
  activo: boolean;
  created_at: string;
}

export interface AdminEvento {
  id: string;
  evento: string;
  recurso: string;
  metodo: string;
  ruta: string;
  created_at: string;
}

export interface AdminExportacion {
  id: string;
  estado: "pendiente" | "procesando" | "lista" | "fallida" | "vencida" | string;
  solicitada_at: string;
  generada_at: string | null;
  vence_at: string | null;
}

export const getAdminPerfil = () => client.get<AdminPerfil>("/api/admin/perfil");
export const updateAdminPerfil = (body: Pick<AdminPerfil, "nombre" | "moneda">) =>
  client.patch<AdminPerfil>("/api/admin/perfil", body);
export const getAdminUsuarios = () => client.get<AdminUsuario[]>("/api/admin/usuarios");
export const createAdminUsuario = (body: {
  email: string;
  nombre: string;
  password_inicial: string;
  rol: string;
}) => client.post<AdminUsuario>("/api/admin/usuarios", body);
export const getAdminAuditoria = (evento: string) => {
  const params = new URLSearchParams({ limit: "100" });
  if (evento) params.set("evento", evento);
  return client.get<AdminEvento[]>(`/api/admin/auditoria?${params}`);
};
export const getAdminExportaciones = () => client.get<AdminExportacion[]>("/api/admin/exportaciones");
export const requestAdminExportacion = () => client.post<AdminExportacion>("/api/admin/exportacion");
export const getAdminExportacion = (id: string) =>
  client.get<AdminExportacion>(`/api/admin/exportacion/${id}`);
export const downloadAdminExportacion = (id: string) =>
  client.download(`/api/admin/exportacion/${id}/descargar`);
