import { useEffect, useState } from "react";
import {
  actualizarAnamnesis,
  crearEvolucion,
  listEvoluciones,
  mensajeError,
  type Evolucion,
  type Historia,
} from "./clinica-api";
import { formatDateTime, shortId } from "../../shared/format";

interface HceTabProps {
  historia: Historia;
  canWrite: boolean;
}

function nullable(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length === 0 ? null : trimmed;
}

/**
 * C-15 HCE tab: anamnesis + append-only evolutions. Corrections are a new
 * evolution pointing at the previous one; no edit/delete is ever offered.
 */
export function HceTab({ historia, canWrite }: HceTabProps): JSX.Element {
  const [evoluciones, setEvoluciones] = useState<Evolucion[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [contenido, setContenido] = useState("");
  const [corrigeId, setCorrigeId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [anamnesis, setAnamnesis] = useState({
    alergias: historia.alergias ?? "",
    medicacion: historia.medicacion ?? "",
    antecedentes: historia.antecedentes ?? "",
  });
  const [editando, setEditando] = useState(false);
  const [guardandoAnamnesis, setGuardandoAnamnesis] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadError(null);
    listEvoluciones(historia.id)
      .then((rows) => {
        if (active) {
          setEvoluciones(rows);
        }
      })
      .catch((cause: unknown) => {
        if (active) {
          setEvoluciones([]);
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
  }, [historia.id]);

  function startCorrection(evolucionId: string): void {
    setCorrigeId(evolucionId);
    setContenido("");
    setError(null);
    setAviso(null);
  }

  function cancelCorrection(): void {
    setCorrigeId(null);
    setContenido("");
    setError(null);
  }

  async function submitEvolucion(): Promise<void> {
    const texto = contenido.trim();
    if (texto.length === 0) {
      setError("Escribí el contenido de la evolución.");
      return;
    }
    setSaving(true);
    setError(null);
    setAviso(null);
    try {
      const nueva = await crearEvolucion(historia.id, texto, corrigeId);
      setEvoluciones((prev) => [...prev, nueva]);
      setContenido("");
      setCorrigeId(null);
      setAviso(
        corrigeId === null
          ? "Evolución registrada."
          : "Corrección registrada como una evolución nueva.",
      );
    } catch (cause: unknown) {
      setError(mensajeError(cause));
    } finally {
      setSaving(false);
    }
  }

  async function submitAnamnesis(): Promise<void> {
    setGuardandoAnamnesis(true);
    setError(null);
    setAviso(null);
    try {
      const actualizada = await actualizarAnamnesis(historia.id, {
        alergias: nullable(anamnesis.alergias),
        medicacion: nullable(anamnesis.medicacion),
        antecedentes: nullable(anamnesis.antecedentes),
      });
      setAnamnesis({
        alergias: actualizada.alergias ?? "",
        medicacion: actualizada.medicacion ?? "",
        antecedentes: actualizada.antecedentes ?? "",
      });
      setEditando(false);
      setAviso("Anamnesis actualizada.");
    } catch (cause: unknown) {
      setError(mensajeError(cause));
    } finally {
      setGuardandoAnamnesis(false);
    }
  }

  const corrige = evoluciones.find((item) => item.id === corrigeId) ?? null;
  const formTitle =
    corrige === null ? "Nueva evolución" : "Corrección de evolución";

  return (
    <div className="ficha-panel">
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

      <section className="ficha-card" aria-labelledby="anamnesis-title">
        <h2 id="anamnesis-title">Anamnesis</h2>
        {editando ? (
          <div className="ficha-grid-2">
            <label>
              Alergias
              <textarea
                value={anamnesis.alergias}
                onChange={(event) =>
                  setAnamnesis((prev) => ({
                    ...prev,
                    alergias: event.target.value,
                  }))
                }
              />
            </label>
            <label>
              Medicación
              <textarea
                value={anamnesis.medicacion}
                onChange={(event) =>
                  setAnamnesis((prev) => ({
                    ...prev,
                    medicacion: event.target.value,
                  }))
                }
              />
            </label>
            <label>
              Antecedentes
              <textarea
                value={anamnesis.antecedentes}
                onChange={(event) =>
                  setAnamnesis((prev) => ({
                    ...prev,
                    antecedentes: event.target.value,
                  }))
                }
              />
            </label>
            <div className="ficha-actions">
              <button
                type="button"
                disabled={guardandoAnamnesis}
                onClick={() => void submitAnamnesis()}
              >
                Guardar anamnesis
              </button>
              <button type="button" onClick={() => setEditando(false)}>
                Cancelar
              </button>
            </div>
          </div>
        ) : (
          <>
            <dl className="ficha-admin">
              <div>
                <dt>Alergias</dt>
                <dd>{anamnesis.alergias || "Sin datos"}</dd>
              </div>
              <div>
                <dt>Medicación</dt>
                <dd>{anamnesis.medicacion || "Sin datos"}</dd>
              </div>
              <div>
                <dt>Antecedentes</dt>
                <dd>{anamnesis.antecedentes || "Sin datos"}</dd>
              </div>
            </dl>
            {canWrite ? (
              <div className="ficha-actions">
                <button type="button" onClick={() => setEditando(true)}>
                  Editar anamnesis
                </button>
              </div>
            ) : null}
          </>
        )}
      </section>

      <section className="ficha-card" aria-labelledby="evoluciones-title">
        <h2 id="evoluciones-title">Evoluciones</h2>
        {loading ? <p role="status">Cargando evoluciones…</p> : null}
        {loadError !== null ? (
          <p role="alert" className="clinica-error">
            {loadError}
          </p>
        ) : null}
        {!loading && loadError === null && evoluciones.length === 0 ? (
          <p className="ficha-empty">Todavía no hay evoluciones registradas.</p>
        ) : null}

        {evoluciones.length > 0 ? (
          <ul className="ficha-list">
            {evoluciones.map((evolucion) => (
              <li key={evolucion.id} className="ficha-list-item">
                <div className="ficha-meta">
                  <span>Autor: {shortId(evolucion.autor_usuario_id)}</span>
                  <span>{formatDateTime(evolucion.created_at)}</span>
                  {evolucion.corrige_evolucion_id !== null ? (
                    <span>
                      Corrige evolución{" "}
                      {shortId(evolucion.corrige_evolucion_id)}
                    </span>
                  ) : null}
                </div>
                <p>{evolucion.contenido}</p>
                {canWrite ? (
                  <button
                    type="button"
                    onClick={() => startCorrection(evolucion.id)}
                  >
                    Corregir evolución
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}

        {canWrite ? (
          <div className="ficha-field" style={{ marginTop: "0.75rem" }}>
            <label htmlFor="evolucion-texto">{formTitle}</label>
            {corrige !== null ? (
              <p className="clinica-muted">
                La corrección se agrega como una evolución nueva que referencia
                la evolución {shortId(corrige.id)}. La original no se modifica.
              </p>
            ) : null}
            <textarea
              id="evolucion-texto"
              value={contenido}
              maxLength={4000}
              onChange={(event) => setContenido(event.target.value)}
            />
            <div className="ficha-actions">
              <button
                type="button"
                disabled={saving}
                onClick={() => void submitEvolucion()}
              >
                {corrige === null ? "Agregar evolución" : "Registrar corrección"}
              </button>
              {corrige !== null ? (
                <button type="button" onClick={cancelCorrection}>
                  Cancelar corrección
                </button>
              ) : null}
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
