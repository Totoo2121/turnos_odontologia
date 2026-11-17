import { useEffect, useState } from "react";
import { useAuthStore } from "../auth/auth-store";
import { formatMoney, todayIso } from "../../shared/format";
import {
  getAusentismo,
  getOcupacion,
  getRecaudacion,
  type Reporte,
  type ReporteRecaudacion,
  type FilaAusentismo,
  type FilaOcupacion,
} from "./reportes-api";
import "./reportes.css";

const today = todayIso();
const monthStart = `${today.slice(0, 7)}-01`;

export function ReportesPage(): JSX.Element {
  const roles = useAuthStore((state) => state.user?.roles ?? []);
  const [desde, setDesde] = useState(monthStart);
  const [hasta, setHasta] = useState(today);
  const [ocupacion, setOcupacion] = useState<Reporte<FilaOcupacion> | null>(null);
  const [ausentismo, setAusentismo] = useState<Reporte<FilaAusentismo> | null>(null);
  const [recaudacion, setRecaudacion] = useState<ReporteRecaudacion | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const owner = roles.includes("propietario");

  useEffect(() => {
    let current = true;
    setLoading(true);
    setError("");
    const requests = [getOcupacion(desde, hasta), getAusentismo(desde, hasta)];
    void Promise.all([
      ...requests,
      ...(owner ? [getRecaudacion(desde, hasta)] : []),
    ]).then((results) => {
      if (!current) return;
      setOcupacion(results[0] as Reporte<FilaOcupacion>);
      setAusentismo(results[1] as Reporte<FilaAusentismo>);
      setRecaudacion(owner ? (results[2] as ReporteRecaudacion) : null);
    }).catch((cause: unknown) => {
      if (current) setError(cause instanceof Error ? cause.message : "No se pudieron cargar los reportes.");
    }).finally(() => {
      if (current) setLoading(false);
    });
    return () => { current = false; };
  }, [desde, hasta, owner]);

  return (
    <section className="reports-page" aria-labelledby="reports-title">
      <header className="reports-header">
        <div>
          <p className="reports-eyebrow">OPERACIÓN · {ocupacion?.alcance ?? "—"}</p>
          <h1 id="reports-title">Reportes</h1>
          <p>Actividad y resultados del período seleccionado.</p>
        </div>
        <div className="reports-dates">
          <label>Desde<input type="date" value={desde} max={hasta} onChange={(event) => setDesde(event.target.value)} /></label>
          <label>Hasta<input type="date" value={hasta} min={desde} onChange={(event) => setHasta(event.target.value)} /></label>
        </div>
      </header>
      {error ? <p role="alert" className="reports-error">{error}</p> : null}
      {loading ? <p role="status">Actualizando reportes…</p> : null}

      <section className="reports-panel" aria-labelledby="occupancy-title">
        <div className="reports-panel-heading"><div><p className="reports-eyebrow">AGENDA</p><h2 id="occupancy-title">Ocupación por profesional</h2></div><span>Minutos reservados</span></div>
        <div className="reports-table-wrap"><table><thead><tr><th>Profesional</th><th>Turnos</th><th>Tiempo ocupado</th><th>Atendidos</th></tr></thead>
          <tbody>{ocupacion?.filas.length === 0 ? <tr><td colSpan={4}>Sin turnos en este período.</td></tr> : ocupacion?.filas.map((row) => <tr key={row.profesional_id}><th scope="row">{row.profesional}</th><td>{row.turnos}</td><td>{Math.floor(row.minutos_ocupados / 60)} h {row.minutos_ocupados % 60} min</td><td>{row.atendidos}</td></tr>)}</tbody>
        </table></div>
        <p className="reports-note">El sistema aún no configura jornadas por profesional; por eso muestra tiempo agendado y no un porcentaje contra capacidad disponible.</p>
      </section>

      <section className="reports-panel" aria-labelledby="absence-title">
        <div className="reports-panel-heading"><div><p className="reports-eyebrow">ASISTENCIA</p><h2 id="absence-title">Ausentismo</h2></div><span>Ausencias y cancelaciones</span></div>
        <div className="reports-table-wrap"><table><thead><tr><th>Profesional</th><th>Turnos</th><th>Ausentes</th><th>Cancelados</th><th>Tasa</th></tr></thead>
          <tbody>{ausentismo?.filas.length === 0 ? <tr><td colSpan={5}>Sin turnos en este período.</td></tr> : ausentismo?.filas.map((row) => <tr key={row.profesional_id}><th scope="row">{row.profesional}</th><td>{row.turnos}</td><td>{row.ausentes}</td><td>{row.cancelados}</td><td>{row.tasa_ausentismo.toFixed(1)}%</td></tr>)}</tbody>
        </table></div>
        <p className="reports-note">La tasa se calcula como ausentes sobre el total de turnos del período.</p>
      </section>

      {owner && recaudacion ? <section className="reports-panel" aria-labelledby="cash-title">
        <div className="reports-panel-heading"><div><p className="reports-eyebrow">FINANZAS · ARS</p><h2 id="cash-title">Recaudación</h2></div><span>Solo propietario</span></div>
        <div className="reports-metrics"><article><span>Total cobrado</span><strong>{formatMoney(recaudacion.total_cobrado)}</strong></article><article><span>Señas acreditadas</span><strong>{formatMoney(recaudacion.senias_acreditadas)}</strong></article><article><span>Cuenta corriente</span><strong>{formatMoney(recaudacion.cobros_cuenta_corriente)}</strong></article><article><span>Deuda de planes</span><strong>{formatMoney(recaudacion.deuda_neta_planes)}</strong></article></div>
        <div className="reports-table-wrap"><table><thead><tr><th>Profesional</th><th>Señas acreditadas</th><th>Cantidad</th></tr></thead><tbody>{recaudacion.por_profesional.length === 0 ? <tr><td colSpan={3}>Sin señas acreditadas en este período.</td></tr> : recaudacion.por_profesional.map((row) => <tr key={row.profesional_id}><th scope="row">{row.profesional}</th><td>{formatMoney(row.senias_acreditadas)}</td><td>{row.cantidad_senias}</td></tr>)}</tbody></table></div>
      </section> : null}
    </section>
  );
}
