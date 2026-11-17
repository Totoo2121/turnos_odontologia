import { useAgendaStore } from "./agenda-store";
import { formatDateTime } from "../../shared/format";

export function DayView(): JSX.Element {
  const { turnos } = useAgendaStore();
  return (
    <div className="agenda-view">
      <div className="agenda-section-heading">
        <h2>Vista día</h2>
        <span>{turnos.length} turnos</span>
      </div>
      {turnos.length === 0 ? <p className="agenda-empty">No hay turnos para esta fecha.</p> : null}
      <ul className="agenda-list">
        {turnos.map((t) => (
          <li key={t.id} className="agenda-item">
            <span className="agenda-time">{formatDateTime(t.inicio)} – {formatDateTime(t.fin)}</span>
            <span className="agenda-status">{t.estado}</span>
            <span className="agenda-detail">Cobro: {t.cobro}{t.sobreturno ? " · Sobreturno" : ""}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
