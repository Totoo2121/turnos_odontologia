import { useEffect, useState, type FormEvent } from "react";
import {
  createAdminUsuario,
  downloadAdminExportacion,
  getAdminAuditoria,
  getAdminExportacion,
  getAdminExportaciones,
  getAdminPerfil,
  getAdminUsuarios,
  requestAdminExportacion,
  updateAdminPerfil,
  type AdminEvento,
  type AdminExportacion,
  type AdminPerfil,
  type AdminUsuario,
} from "./admin-api";
import "./admin.css";

function dateTime(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("es-AR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

export default function AdminPage(): JSX.Element {
  const [perfil, setPerfil] = useState<AdminPerfil | null>(null);
  const [usuarios, setUsuarios] = useState<AdminUsuario[]>([]);
  const [eventos, setEventos] = useState<AdminEvento[]>([]);
  const [exportaciones, setExportaciones] = useState<AdminExportacion[]>([]);
  const [eventoFiltro, setEventoFiltro] = useState("");
  const [loading, setLoading] = useState(true);
  const [savingPerfil, setSavingPerfil] = useState(false);
  const [savingUsuario, setSavingUsuario] = useState(false);
  const [requestingExport, setRequestingExport] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [nombre, setNombre] = useState("");
  const [email, setEmail] = useState("");
  const [nombreUsuario, setNombreUsuario] = useState("");
  const [passwordInicial, setPasswordInicial] = useState("");
  const [rol, setRol] = useState("recepcion");

  async function loadAll(filter = eventoFiltro): Promise<void> {
    setLoading(true);
    setError("");
    try {
      const [profile, team, audit, jobs] = await Promise.all([
        getAdminPerfil(), getAdminUsuarios(), getAdminAuditoria(filter), getAdminExportaciones(),
      ]);
      setPerfil(profile);
      setNombre(profile.nombre);
      setUsuarios(team);
      setEventos(audit);
      setExportaciones(jobs);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo cargar Administración.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadAll(); }, []);

  async function saveProfile(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setSavingPerfil(true); setError(""); setNotice("");
    try {
      const updated = await updateAdminPerfil({ nombre: nombre.trim(), moneda: "ARS" });
      setPerfil(updated); setNombre(updated.nombre); setNotice("Datos de la clínica actualizados.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo guardar el perfil.");
    } finally { setSavingPerfil(false); }
  }

  async function addUser(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault(); setSavingUsuario(true); setError(""); setNotice("");
    try {
      await createAdminUsuario({ email: email.trim(), nombre: nombreUsuario.trim(), password_inicial: passwordInicial, rol });
      setEmail(""); setNombreUsuario(""); setPasswordInicial("");
      setNotice("Usuario creado. Compartí la contraseña inicial fuera del sistema.");
      await loadAll();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo crear el usuario.");
    } finally { setSavingUsuario(false); }
  }

  async function startExport(): Promise<void> {
    setRequestingExport(true); setError(""); setNotice("");
    try {
      await requestAdminExportacion();
      setNotice("Exportación solicitada. Actualizá el estado para ver cuándo está lista.");
      const jobs = await getAdminExportaciones(); setExportaciones(jobs);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo solicitar la exportación.");
    } finally { setRequestingExport(false); }
  }

  async function refreshExport(id: string): Promise<void> {
    try {
      const updated = await getAdminExportacion(id);
      setExportaciones((current) => current.map((job) => job.id === id ? updated : job));
      setError("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "No se pudo consultar la exportación."); }
  }

  async function downloadExport(id: string): Promise<void> {
    try {
      const blob = await downloadAdminExportacion(id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = `exportacion-${id}.zip`;
      anchor.click(); URL.revokeObjectURL(url);
      setNotice("Exportación descargada. El archivo queda disponible una sola vez.");
      await loadAll();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "No se pudo descargar la exportación."); }
  }

  return (
    <section className="admin-page" aria-labelledby="admin-title">
      <header className="admin-header">
        <div><p className="admin-eyebrow">GESTIÓN DEL CONSULTORIO</p><h1 id="admin-title">Administración</h1><p>Perfil, equipo y control de datos de tu clínica.</p></div>
        <button type="button" onClick={() => void loadAll()} disabled={loading}>Actualizar datos</button>
      </header>
      {error ? <p role="alert" className="admin-alert admin-alert-error">{error}</p> : null}
      {notice ? <p role="status" className="admin-alert admin-alert-success">{notice}</p> : null}
      {loading ? <p role="status">Cargando administración…</p> : null}
      {!loading && !perfil && !error ? <p role="status">No se encontró el perfil de esta clínica.</p> : null}

      {perfil ? <div className="admin-grid">
        <section className="admin-panel" aria-labelledby="profile-title">
          <div className="admin-panel-heading"><div><p className="admin-eyebrow">CONSULTORIO</p><h2 id="profile-title">Perfil de la clínica</h2></div><span className="admin-slug">/{perfil.slug_reserva}</span></div>
          <form className="admin-form" onSubmit={(event) => void saveProfile(event)}>
            <label>Nombre de la clínica<input value={nombre} onChange={(event) => setNombre(event.target.value)} minLength={2} maxLength={160} required /></label>
            <label>Moneda<select value="ARS" disabled aria-label="Moneda (única moneda disponible)"><option value="ARS">ARS · Peso argentino</option></select></label>
            <p className="admin-help">El identificador de reserva y el plan no se pueden cambiar desde esta pantalla.</p>
            <button type="submit" disabled={savingPerfil || nombre.trim() === perfil.nombre}>{savingPerfil ? "Guardando…" : "Guardar cambios"}</button>
          </form>
        </section>

        <section className="admin-panel" aria-labelledby="team-title">
          <div className="admin-panel-heading"><div><p className="admin-eyebrow">ACCESO</p><h2 id="team-title">Equipo</h2></div><span>{usuarios.length} {usuarios.length === 1 ? "usuario" : "usuarios"}</span></div>
          <div className="admin-table-wrap"><table><thead><tr><th>Nombre</th><th>Email</th><th>Rol</th><th>Estado</th></tr></thead><tbody>
            {usuarios.length ? usuarios.map((user) => <tr key={user.id}><th scope="row">{user.nombre || "—"}</th><td>{user.email}</td><td>{user.rol}</td><td><span className={`admin-badge ${user.activo ? "is-active" : "is-inactive"}`}>{user.activo ? "Activo" : "Inactivo"}</span></td></tr>) : <tr><td colSpan={4}>Todavía no hay usuarios en el equipo.</td></tr>}
          </tbody></table></div>
          <form className="admin-form admin-user-form" onSubmit={(event) => void addUser(event)}>
            <h3>Agregar usuario</h3>
            <label>Nombre<input value={nombreUsuario} onChange={(event) => setNombreUsuario(event.target.value)} minLength={2} maxLength={160} autoComplete="name" required /></label>
            <label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} maxLength={254} autoComplete="email" required /></label>
            <label>Rol<select value={rol} onChange={(event) => setRol(event.target.value)}><option value="recepcion">Recepción</option><option value="odontologo">Odontólogo</option><option value="asistente">Asistente</option></select></label>
            <label>Contraseña inicial<input type="password" value={passwordInicial} onChange={(event) => setPasswordInicial(event.target.value)} minLength={10} maxLength={256} autoComplete="new-password" required /><span className="admin-help">Mínimo 10 caracteres. El sistema guarda solo un hash seguro.</span></label>
            <button type="submit" disabled={savingUsuario}>{savingUsuario ? "Creando…" : "Crear usuario"}</button>
          </form>
        </section>

        <section className="admin-panel" aria-labelledby="audit-title">
          <div className="admin-panel-heading"><div><p className="admin-eyebrow">TRAZABILIDAD</p><h2 id="audit-title">Auditoría reciente</h2></div></div>
          <form className="admin-filter" onSubmit={(event) => { event.preventDefault(); void loadAll(eventoFiltro); }}>
            <label htmlFor="audit-filter">Filtrar por tipo de evento</label><input id="audit-filter" value={eventoFiltro} onChange={(event) => setEventoFiltro(event.target.value)} maxLength={64} placeholder="Ej.: recurso_consultado" />
            <button type="submit" disabled={loading}>Filtrar</button>
          </form>
          <div className="admin-table-wrap"><table><thead><tr><th>Fecha</th><th>Evento</th><th>Recurso</th><th>Método</th></tr></thead><tbody>
            {eventos.length ? eventos.map((item) => <tr key={item.id}><td>{dateTime(item.created_at)}</td><td>{item.evento}</td><td>{item.recurso}</td><td>{item.metodo}</td></tr>) : <tr><td colSpan={4}>No hay eventos para este filtro.</td></tr>}
          </tbody></table></div>
        </section>

        <section className="admin-panel" aria-labelledby="exports-title">
          <div className="admin-panel-heading"><div><p className="admin-eyebrow">PORTABILIDAD</p><h2 id="exports-title">Exportación de datos</h2></div></div>
          <p className="admin-help">El archivo contiene los datos del tenant. Las descargas vencen y están disponibles una sola vez.</p>
          <button type="button" onClick={() => void startExport()} disabled={requestingExport}>{requestingExport ? "Solicitando…" : "Solicitar exportación"}</button>
          <ul className="admin-export-list">{exportaciones.length ? exportaciones.map((job) => <li key={job.id}>
            <span><strong>{job.estado}</strong><small>Solicitada {dateTime(job.solicitada_at)}</small></span>
            <span className="admin-export-actions"><button type="button" onClick={() => void refreshExport(job.id)}>Actualizar estado</button>{job.estado === "lista" ? <button type="button" onClick={() => void downloadExport(job.id)}>Descargar ZIP</button> : null}</span>
          </li>) : <li className="admin-empty">Todavía no hay exportaciones.</li>}</ul>
        </section>
      </div> : null}
    </section>
  );
}
