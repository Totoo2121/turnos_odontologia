import { useEffect, useState } from "react";
import { addDaysIso, todayIso } from "../../shared/format";
import { useAgendaStore } from "./agenda-store";
import { fetchAgenda } from "./agenda-api";
import { DayView } from "./DayView";
import { WeekView } from "./WeekView";
import "./agenda.css";

export function AgendaPage(): JSX.Element {
  const { vista, fecha, setFecha, setTurnos } = useAgendaStore();
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);
    setTurnos([]);
    fetchAgenda(fecha, vista)
      .then((data) => { if (active) setTurnos(Array.isArray(data) ? data : []); })
      .catch(() => { if (active) setError(true); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [fecha, vista, setTurnos]);
  return (
    <section className="agenda-page">
      <header className="agenda-header">
        <h1>Agenda</h1>
        <div className="agenda-view-toggle" role="group" aria-label="Vista de agenda">
          <button aria-pressed={vista === "dia"} onClick={() => useAgendaStore.getState().setVista("dia")}>Día</button>
          <button aria-pressed={vista === "semana"} onClick={() => useAgendaStore.getState().setVista("semana")}>Semana</button>
        </div>
      </header>
      <div className="agenda-date-controls">
        <button type="button" onClick={() => setFecha(addDaysIso(fecha, vista === "dia" ? -1 : -7))}>Anterior</button>
        <label>Fecha de agenda<input type="date" value={fecha} required onChange={(event) => { if (event.target.value) setFecha(event.target.value); }} /></label>
        <button type="button" onClick={() => setFecha(addDaysIso(fecha, vista === "dia" ? 1 : 7))}>Siguiente</button>
        <button type="button" onClick={() => setFecha(todayIso())}>Hoy</button>
      </div>
      {error ? <p role="alert">No se pudo cargar la agenda. Volvé a seleccionar la fecha para reintentar.</p> : loading ? <p role="status">Cargando agenda…</p> : vista === "dia" ? <DayView /> : <WeekView />}
    </section>
  );
}
