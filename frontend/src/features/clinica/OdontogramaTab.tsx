import { useEffect, useState } from "react";
import { Modal } from "../../shared/ui/Modal";
import {
  ESTADOS_PIEZA,
  ESTADOS_SIN_SUPERFICIE,
  SUPERFICIES,
  crearEventoPieza,
  getOdontograma,
  mensajeError,
  validarEventoPieza,
  type EstadoPieza,
  type EstadoPiezaActual,
  type Odontograma,
  type Superficie,
} from "./clinica-api";

interface OdontogramaTabProps {
  historiaId: string;
  canWrite: boolean;
}

/** Four quadrants, 8 permanent FDI pieces each — 32 total. */
const ARCADAS: { label: string; piezas: number[] }[] = [
  { label: "Arcada superior derecha", piezas: [18, 17, 16, 15, 14, 13, 12, 11] },
  { label: "Arcada superior izquierda", piezas: [21, 22, 23, 24, 25, 26, 27, 28] },
  { label: "Arcada inferior izquierda", piezas: [31, 32, 33, 34, 35, 36, 37, 38] },
  { label: "Arcada inferior derecha", piezas: [48, 47, 46, 45, 44, 43, 42, 41] },
];

export const PIEZAS_FDI = ARCADAS.flatMap((arcada) => arcada.piezas);

function formatEvento(estado: EstadoPiezaActual): string {
  return estado.superficie === null
    ? estado.estado
    : `${estado.estado} (${estado.superficie})`;
}

/**
 * C-15 odontogram tab. Client-side validation mirrors C-13, so an invalid
 * estado–superficie pair never reaches the API and the grid stays untouched.
 */
export function OdontogramaTab({
  historiaId,
  canWrite,
}: OdontogramaTabProps): JSX.Element {
  const [odontograma, setOdontograma] = useState<Odontograma | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [pieza, setPieza] = useState<number | null>(null);
  const [estado, setEstado] = useState<EstadoPieza>("caries");
  const [superficie, setSuperficie] = useState<Superficie | "">("");
  const [observaciones, setObservaciones] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadError(null);
    getOdontograma(historiaId)
      .then((data) => {
        if (active) {
          setOdontograma(data);
        }
      })
      .catch((cause: unknown) => {
        if (active) {
          setOdontograma(null);
          setLoadError(mensajeError(cause));
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
  }, [historiaId]);

  function estadoDePieza(numero: number): EstadoPiezaActual[] {
    return (odontograma?.estado_actual ?? []).filter(
      (item) => item.pieza_fdi === numero,
    );
  }

  function abrirPieza(numero: number): void {
    const actuales = estadoDePieza(numero);
    const ultimo = actuales[actuales.length - 1];
    setPieza(numero);
    setEstado(ultimo?.estado ?? "caries");
    setSuperficie(ultimo?.superficie ?? "");
    setObservaciones("");
    setFormError(null);
    setAviso(null);
  }

  function cerrarModal(): void {
    setPieza(null);
    setFormError(null);
  }

  async function submitEvento(): Promise<void> {
    if (pieza === null) {
      return;
    }
    const superficieValue = superficie === "" ? null : superficie;
    const validation = validarEventoPieza(estado, superficieValue);
    if (validation !== null) {
      setFormError(validation);
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      const evento = await crearEventoPieza(historiaId, {
        pieza_fdi: pieza,
        estado,
        superficie: superficieValue,
        observaciones:
          observaciones.trim().length === 0 ? null : observaciones.trim(),
      });
      const actualizado: EstadoPiezaActual = {
        pieza_fdi: evento.pieza_fdi,
        superficie: evento.superficie,
        estado: evento.estado,
        fecha: evento.fecha,
        evento_id: evento.id,
        autor_usuario_id: evento.autor_usuario_id,
        autor_profesional_id: evento.autor_profesional_id ?? null,
      };
      setOdontograma((prev) =>
        prev === null
          ? prev
          : {
              ...prev,
              estado_actual: [
                ...prev.estado_actual.filter(
                  (item) =>
                    !(
                      item.pieza_fdi === actualizado.pieza_fdi &&
                      item.superficie === actualizado.superficie
                    ),
                ),
                actualizado,
              ],
            },
      );
      setPieza(null);
      setAviso(`Evento registrado en la pieza ${actualizado.pieza_fdi}.`);
    } catch (cause: unknown) {
      // A 422 keeps the modal open and the grid exactly as it was.
      setFormError(mensajeError(cause));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="ficha-panel">
      {loadError !== null ? (
        <p role="alert" className="clinica-error">
          {loadError}
        </p>
      ) : null}
      {aviso !== null ? (
        <p role="status" className="clinica-success">
          {aviso}
        </p>
      ) : null}

      <section className="ficha-card" aria-labelledby="odontograma-title">
        <h2 id="odontograma-title">Odontograma FDI</h2>
        <p className="clinica-muted">
          32 piezas permanentes. Seleccioná una pieza para registrar un evento
          clínico.
        </p>
        {loading ? <p role="status">Cargando odontograma…</p> : null}
        <div className="odontograma">
          {ARCADAS.map((arcada) => (
            <div key={arcada.label} className="arcada">
              <h4>{arcada.label}</h4>
              <div className="arcada-piezas">
                {arcada.piezas.map((numero) => {
                  const estados = estadoDePieza(numero);
                  return (
                    <button
                      key={numero}
                      type="button"
                      className="pieza"
                      data-tiene-estado={estados.length > 0}
                      aria-label={`Pieza ${numero}`}
                      disabled={!canWrite || loading}
                      onClick={() => abrirPieza(numero)}
                    >
                      <span className="pieza-numero">{numero}</span>
                      <span className="pieza-estado">
                        {estados.length === 0
                          ? "sin registro"
                          : estados.map(formatEvento).join(" · ")}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </section>

      <Modal
        open={pieza !== null}
        onClose={cerrarModal}
        title={pieza === null ? "Evento de pieza" : `Pieza ${pieza}`}
      >
        <div className="ficha-field">
          <label htmlFor="evento-estado">Estado</label>
          <select
            id="evento-estado"
            value={estado}
            onChange={(event) => {
              const next = event.target.value as EstadoPieza;
              setEstado(next);
              if (ESTADOS_SIN_SUPERFICIE.has(next)) {
                setSuperficie("");
              }
            }}
          >
            {ESTADOS_PIEZA.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>

          <label htmlFor="evento-superficie">Superficie</label>
          <select
            id="evento-superficie"
            value={superficie}
            onChange={(event) =>
              setSuperficie(event.target.value as Superficie | "")
            }
          >
            <option value="">Sin superficie</option>
            {SUPERFICIES.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>

          <label htmlFor="evento-observaciones">Observaciones</label>
          <textarea
            id="evento-observaciones"
            value={observaciones}
            onChange={(event) => setObservaciones(event.target.value)}
          />

          {formError !== null ? (
            <p role="alert" className="clinica-error">
              {formError}
            </p>
          ) : null}

          <div className="ficha-actions">
            <button
              type="button"
              disabled={saving}
              onClick={() => void submitEvento()}
            >
              Registrar evento
            </button>
            <button type="button" onClick={cerrarModal}>
              Cancelar
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
