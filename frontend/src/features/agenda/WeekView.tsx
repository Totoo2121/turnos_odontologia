import { useAgendaStore } from "./agenda-store";
import { formatDateTime } from "../../shared/format";

export function WeekView(): JSX.Element {
  const { turnos } = useAgendaStore();
  return (
    <div className="agenda-view">
      <div className="agenda-section-heading">
        <h2>Vista semana</h2>
      </div>
      {turnos.length === 0 ? <p className="agenda-empty">No hay turnos para esta semana.</p> : null}
      <ul className="agenda-list">
        {turnos.map((t) => (
          <li key={t.id} className="agenda-item agenda-item-compact">
            <span className="agenda-time">{formatDateTime(t.inicio)}</span>
            <span className="agenda-status">{t.estado}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
