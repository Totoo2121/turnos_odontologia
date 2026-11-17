import { useEffect, useState } from "react";
import { addDaysIso, formatDateTime, todayIso } from "../../shared/format";
import {
  cambiarEstadoTurno,
  crearTurnoControl,
  listPrestaciones,
  listProfesionales,
  listSillones,
  listTurnosDia,
  mensajeError,
  type AgendaTurno,
  type Prestacion,
  type Profesional,
  type Sillon,
} from "./clinica-api";

interface TurnoPanelProps {
  pacienteId: string;
  canClose: boolean;
  canSchedule: boolean;
}

const ESTADOS_CERRADOS = new Set(["atendido", "ausente", "cancelado"]);

function displayDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

function estadoLabel(estado: string): string {
  return estado.charAt(0).toUpperCase() + estado.slice(1);
}

/**
 * C-15 turn panel: closes the open appointment as attended and suggests the
 * recall date. Only agenda-C roles can actually schedule the follow-up.
 */
export function TurnoPanel({
  pacienteId,
  canClose,
  canSchedule,
}: TurnoPanelProps): JSX.Element {
  const [turnos, setTurnos] = useState<AgendaTurno[]>([]);
  const [prestaciones, setPrestaciones] = useState<Prestacion[]>([]);
  const [profesionales, setProfesionales] = useState<Profesional[]>([]);
  const [sillones, setSillones] = useState<Sillon[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const [profesionalId, setProfesionalId] = useState("");
  const [sillonId, setSillonId] = useState("");
  const [prestacionId, setPrestacionId] = useState("");
  const [fecha, setFecha] = useState("");
  const [hora, setHora] = useState("09:00");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    const dia = todayIso();
    const peticiones: [
      Promise<AgendaTurno[]>,
      Promise<Prestacion[]>,
      Promise<Profesional[] | null>,
      Promise<Sillon[] | null>,
    ] = [
      listTurnosDia(dia),
      listPrestaciones(),
      canSchedule ? listProfesionales() : Promise.resolve(null),
      canSchedule ? listSillones() : Promise.resolve(null),
    ];
    Promise.all(peticiones)
      .then(([agenda, catalogo, profesionalesData, sillonesData]) => {
        if (!active) {
          return;
        }
        const delPaciente = agenda
          .filter((turno) => turno.paciente_id === pacienteId)
          .sort((a, b) => a.inicio.localeCompare(b.inicio));
        setTurnos(delPaciente);
        setPrestaciones(catalogo);
        setProfesionales(profesionalesData ?? []);
        setSillones(sillonesData ?? []);
        const abierto =
          delPaciente.find((turno) => !ESTADOS_CERRADOS.has(turno.estado)) ??
          delPaciente[0];
        const prestacion = catalogo.find(
          (item) => item.id === abierto?.prestacion_id,
        );
        if (abierto?.prestacion_id) {
          setPrestacionId(abierto.prestacion_id);
        }
        if (
          prestacion?.intervalo_control_dias !== null &&
          prestacion?.intervalo_control_dias !== undefined
        ) {
          setFecha(
            addDaysIso(dia, prestacion.intervalo_control_dias),
          );
        }
        const primerProfesional = (profesionalesData ?? []).find(
          (item) => item.activo,
        );
        if (primerProfesional) {
          setProfesionalId(primerProfesional.id);
        }
        const primerSillon = (sillonesData ?? []).find((item) => item.activo);
        if (primerSillon) {
          setSillonId(primerSillon.id);
        }
      })
      .catch((cause: unknown) => {
        if (active) {
          setTurnos([]);
          setError(mensajeError(cause));
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [pacienteId, canSchedule]);

  const abierto =
    turnos.find((turno) => !ESTADOS_CERRADOS.has(turno.estado)) ?? null;
  const referencia = abierto ?? turnos[0] ?? null;
  const prestacionReferencia = prestaciones.find(
    (item) => item.id === referencia?.prestacion_id,
  );
  const intervalo = prestacionReferencia?.intervalo_control_dias ?? null;
  const controlSugerido =
    intervalo !== null ? addDaysIso(todayIso(), intervalo) : null;

  async function marcarAtendido(turnoId: string): Promise<void> {
    setBusyId(turnoId);
    setError(null);
    setAviso(null);
    try {
      const actualizado = await cambiarEstadoTurno(turnoId, "atendido");
      setTurnos((prev) =>
        prev.map((turno) =>
          turno.id === turnoId ? { ...turno, estado: actualizado.estado } : turno,
        ),
      );
      setAviso("Turno cerrado como atendido.");
    } catch (cause: unknown) {
      setError(mensajeError(cause));
    } finally {
      setBusyId(null);
    }
  }

  async function agendarControl(): Promise<void> {
    setError(null);
    setAviso(null);
    if (
      profesionalId === "" ||
      sillonId === "" ||
      prestacionId === "" ||
      fecha === "" ||
      hora === ""
    ) {
      setError("Completá profesional, sillón, prestación, fecha y hora.");
      return;
    }
    setSaving(true);
    try {
      const nuevo = await crearTurnoControl({
        paciente_id: pacienteId,
        profesional_id: profesionalId,
        sillon_id: sillonId,
        prestacion_id: prestacionId,
        inicio: `${fecha}T${hora}:00`,
      });
      setTurnos((prev) => [
        ...prev,
        {
          id: nuevo.id,
          inicio: nuevo.inicio,
          fin: nuevo.fin,
          estado: nuevo.estado,
          profesional_id: nuevo.profesional_id,
          sillon_id: nuevo.sillon_id,
          prestacion_id: nuevo.prestacion_id,
          paciente_id: nuevo.paciente_id,
          sobreturno: nuevo.sobreturno,
          cobro: "sin-sena",
          cobro_monto: null,
        },
      ]);
      setAviso("Turno de control agendado.");
    } catch (cause: unknown) {
      setError(mensajeError(cause));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="ficha-card" aria-labelledby="turno-panel-title">
      <h2 id="turno-panel-title">Turno y control</h2>
      {loading ? <p role="status">Cargando turnos del día…</p> : null}
      {error !== null ? (
        <p role="alert" className="clinica-error">
          {error}
        </p>
      ) : null}
      {aviso !== null ? (
        <p role="status" className="clinica-success">
          {aviso}
        </p>
      ) : null}

      {!loading && turnos.length === 0 ? (
        <p className="ficha-empty">El paciente no tiene turnos agendados hoy.</p>
      ) : null}

      {turnos.length > 0 ? (
        <ul className="ficha-list">
          {turnos.map((turno) => (
            <li key={turno.id} className="ficha-list-item">
              <div className="ficha-meta">
                <span
                  className="ficha-badge"
                  data-estado={turno.estado}
                >
                  {estadoLabel(turno.estado)}
                </span>
                <span>{formatDateTime(turno.inicio)}</span>
                <span>Cobro: {turno.cobro}</span>
              </div>
              {canClose ? (
                <button
                  type="button"
                  disabled={
                    busyId === turno.id || ESTADOS_CERRADOS.has(turno.estado)
                  }
                  onClick={() => void marcarAtendido(turno.id)}
                >
                  Marcar atendido
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      <p className="clinica-muted">
        {controlSugerido !== null
          ? `Control sugerido: ${displayDate(controlSugerido)} (cada ${intervalo} días).`
          : "Sin intervalo de control configurado para la prestación."}
      </p>

      {canSchedule ? (
        <>
          <h3>Agendar control</h3>
          <div className="ficha-grid-2">
            <label>
              Profesional
              <select
                value={profesionalId}
                onChange={(event) => setProfesionalId(event.target.value)}
              >
                <option value="">Elegir profesional</option>
                {profesionales
                  .filter((item) => item.activo)
                  .map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.nombre}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Sillón
              <select
                value={sillonId}
                onChange={(event) => setSillonId(event.target.value)}
              >
                <option value="">Elegir sillón</option>
                {sillones
                  .filter((item) => item.activo)
                  .map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.nombre}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Prestación
              <select
                value={prestacionId}
                onChange={(event) => setPrestacionId(event.target.value)}
              >
                <option value="">Elegir prestación</option>
                {prestaciones
                  .filter((item) => item.is_active)
                  .map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.nombre}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Fecha
              <input
                type="date"
                value={fecha}
                onChange={(event) => setFecha(event.target.value)}
              />
            </label>
            <label>
              Hora
              <input
                type="time"
                value={hora}
                onChange={(event) => setHora(event.target.value)}
              />
            </label>
          </div>
          <div className="ficha-actions">
            <button
              type="button"
              disabled={saving}
              onClick={() => void agendarControl()}
            >
              Agendar control
            </button>
          </div>
        </>
      ) : null}
    </section>
  );
}
