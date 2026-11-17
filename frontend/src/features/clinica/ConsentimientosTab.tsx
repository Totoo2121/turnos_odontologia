import { useEffect, useState } from "react";
import { formatDateTime, shortId } from "../../shared/format";
import {
  abrirBlob,
  crearConsentimiento,
  descargarConsentimientoPdf,
  listConsentimientos,
  mensajeError,
  type Consentimiento,
} from "./clinica-api";

interface ConsentimientosTabProps {
  pacienteId: string;
  historiaId: string;
  canWrite: boolean;
}

const TIPOS = ["tratamiento", "invasivo", "cirugia", "ortodoncia", "datos"];

function esInvasivo(tipo: string): boolean {
  return tipo === "invasivo" || tipo === "cirugia";
}

/** C-15 consent tab: signature, hash verification and PDF download. */
export function ConsentimientosTab({
  pacienteId,
  historiaId,
  canWrite,
}: ConsentimientosTabProps): JSX.Element {
  const [consentimientos, setConsentimientos] = useState<Consentimiento[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const [tipo, setTipo] = useState("tratamiento");
  const [texto, setTexto] = useState("");
  const [version, setVersion] = useState("v1");
  const [firmante, setFirmante] = useState("");
  const [dni, setDni] = useState("");
  const [planInvasivo, setPlanInvasivo] = useState(false);
  const [saving, setSaving] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadError(null);
    listConsentimientos(pacienteId)
      .then((rows) => {
        if (active) {
          setConsentimientos(rows);
        }
      })
      .catch((cause: unknown) => {
        if (active) {
          setConsentimientos([]);
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
  }, [pacienteId]);

  async function submitConsentimiento(): Promise<void> {
    setError(null);
    setAviso(null);
    if (texto.trim().length === 0) {
      setError("El texto del consentimiento es obligatorio.");
      return;
    }
    if (version.trim().length === 0) {
      setError("La versión del texto es obligatoria.");
      return;
    }
    if (firmante.trim().length === 0) {
      setError("El nombre del firmante es obligatorio.");
      return;
    }
    setSaving(true);
    try {
      const creado = await crearConsentimiento({
        historia_clinica_id: historiaId,
        tipo,
        texto: texto.trim(),
        texto_version: version.trim(),
        firmante_nombre: firmante.trim(),
        firmante_dni: dni.trim().length === 0 ? null : dni.trim(),
        plan_invasivo: planInvasivo || esInvasivo(tipo),
      });
      setConsentimientos((prev) => [creado, ...prev]);
      setTexto("");
      setFirmante("");
      setDni("");
      setAviso("Consentimiento firmado y guardado.");
    } catch (cause: unknown) {
      setError(mensajeError(cause));
    } finally {
      setSaving(false);
    }
  }

  async function abrirPdf(consentimientoId: string): Promise<void> {
    setDownloadingId(consentimientoId);
    setError(null);
    try {
      const blob = await descargarConsentimientoPdf(consentimientoId);
      abrirBlob(blob, `consentimiento-${shortId(consentimientoId)}.pdf`);
    } catch (cause: unknown) {
      setError(mensajeError(cause));
    } finally {
      setDownloadingId(null);
    }
  }

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

      <section className="ficha-card" aria-labelledby="consentimientos-title">
        <h2 id="consentimientos-title">Consentimientos</h2>
        {loading ? <p role="status">Cargando consentimientos…</p> : null}
        {loadError !== null ? (
          <p role="alert" className="clinica-error">
            {loadError}
          </p>
        ) : null}
        {!loading && loadError === null && consentimientos.length === 0 ? (
          <p className="ficha-empty">
            Todavía no hay consentimientos firmados.
          </p>
        ) : null}
        {consentimientos.length > 0 ? (
          <ul className="ficha-list">
            {consentimientos.map((consentimiento) => (
              <li key={consentimiento.id} className="ficha-list-item">
                <div className="ficha-meta">
                  <strong>{consentimiento.tipo}</strong>
                  <span
                    className="ficha-badge"
                    data-tone={consentimiento.hash_valido ? "ok" : "bad"}
                  >
                    {consentimiento.hash_valido
                      ? "Hash verificado"
                      : "Hash inválido"}
                  </span>
                  <span>Firmante: {consentimiento.firmante_nombre}</span>
                  <span>{formatDateTime(consentimiento.firmado_at)}</span>
                  <span>Versión: {consentimiento.texto_version}</span>
                </div>
                <p>{consentimiento.texto}</p>
                <button
                  type="button"
                  disabled={downloadingId === consentimiento.id}
                  onClick={() => void abrirPdf(consentimiento.id)}
                >
                  Abrir PDF
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      {canWrite ? (
        <section className="ficha-card" aria-labelledby="firmar-title">
          <h2 id="firmar-title">Firmar consentimiento</h2>
          <div className="ficha-grid-2">
            <label>
              Tipo
              <select
                value={tipo}
                onChange={(event) => {
                  const next = event.target.value;
                  setTipo(next);
                  setPlanInvasivo(esInvasivo(next));
                }}
              >
                {TIPOS.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Versión del texto
              <input
                value={version}
                maxLength={40}
                onChange={(event) => setVersion(event.target.value)}
              />
            </label>
            <label>
              Firmante
              <input
                value={firmante}
                maxLength={160}
                placeholder="Nombre ficticio"
                onChange={(event) => setFirmante(event.target.value)}
              />
            </label>
            <label>
              DNI del firmante
              <input
                value={dni}
                maxLength={20}
                placeholder="DNI ficticio"
                onChange={(event) => setDni(event.target.value)}
              />
            </label>
          </div>
          <div className="ficha-field">
            <label htmlFor="consentimiento-texto">Texto del consentimiento</label>
            <textarea
              id="consentimiento-texto"
              value={texto}
              onChange={(event) => setTexto(event.target.value)}
            />
          </div>
          <label style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
            <input
              type="checkbox"
              checked={planInvasivo}
              onChange={(event) => setPlanInvasivo(event.target.checked)}
            />
            Plan invasivo
          </label>
          <div className="ficha-actions">
            <button
              type="button"
              disabled={saving}
              onClick={() => void submitConsentimiento()}
            >
              Firmar consentimiento
            </button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
