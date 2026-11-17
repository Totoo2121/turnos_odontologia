import { useEffect, useState } from "react";
import {
  listAdjuntos,
  mensajeError,
  subirAdjunto,
  urlAdjunto,
  type Adjunto,
} from "./clinica-api";

interface AdjuntosTabProps {
  historiaId: string;
  canWrite: boolean;
}

const TIPOS = ["rx", "foto", "documento"] as const;

function formatBytes(size: number): string {
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${Math.round(size / 1024)} KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

/** C-15 attachments tab: multipart upload + signed-URL opening. */
export function AdjuntosTab({
  historiaId,
  canWrite,
}: AdjuntosTabProps): JSX.Element {
  const [adjuntos, setAdjuntos] = useState<Adjunto[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const [tipo, setTipo] = useState<string>("rx");
  const [origen, setOrigen] = useState("");
  const [archivo, setArchivo] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const [saving, setSaving] = useState(false);
  const [openingId, setOpeningId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadError(null);
    listAdjuntos(historiaId)
      .then((rows) => {
        if (active) {
          setAdjuntos(rows);
        }
      })
      .catch((cause: unknown) => {
        if (active) {
          setAdjuntos([]);
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

  async function submitAdjunto(): Promise<void> {
    if (archivo === null) {
      setError("Elegí un archivo para subir.");
      return;
    }
    setSaving(true);
    setError(null);
    setAviso(null);
    try {
      const subido = await subirAdjunto(historiaId, {
        tipo,
        archivo,
        origen: origen.trim().length === 0 ? null : origen.trim(),
      });
      setAdjuntos((prev) => [...prev, subido]);
      setArchivo(null);
      setOrigen("");
      setFileKey((prev) => prev + 1);
      setAviso("Adjunto subido a la historia clínica.");
    } catch (cause: unknown) {
      setError(mensajeError(cause));
    } finally {
      setSaving(false);
    }
  }

  async function abrirAdjunto(adjuntoId: string): Promise<void> {
    setOpeningId(adjuntoId);
    setError(null);
    try {
      const firmada = await urlAdjunto(adjuntoId);
      window.open(firmada.url, "_blank", "noopener,noreferrer");
    } catch (cause: unknown) {
      setError(mensajeError(cause));
    } finally {
      setOpeningId(null);
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

      <section className="ficha-card" aria-labelledby="adjuntos-title">
        <h2 id="adjuntos-title">Adjuntos clínicos</h2>
        {loading ? <p role="status">Cargando adjuntos…</p> : null}
        {loadError !== null ? (
          <p role="alert" className="clinica-error">
            {loadError}
          </p>
        ) : null}
        {!loading && loadError === null && adjuntos.length === 0 ? (
          <p className="ficha-empty">Todavía no hay adjuntos en la historia.</p>
        ) : null}

        {adjuntos.length > 0 ? (
          <ul className="ficha-list">
            {adjuntos.map((adjunto) => (
              <li key={adjunto.id} className="ficha-list-item">
                <div className="ficha-meta">
                  <strong>{adjunto.nombre_original}</strong>
                  <span>Tipo: {adjunto.tipo}</span>
                  <span>{formatBytes(adjunto.size_bytes)}</span>
                  {adjunto.origen !== null ? (
                    <span>Origen: {adjunto.origen}</span>
                  ) : null}
                </div>
                <button
                  type="button"
                  disabled={openingId === adjunto.id}
                  onClick={() => void abrirAdjunto(adjunto.id)}
                >
                  Abrir adjunto
                </button>
              </li>
            ))}
          </ul>
        ) : null}

        {canWrite ? (
          <div className="ficha-grid-2" style={{ marginTop: "0.9rem" }}>
            <label>
              Tipo
              <select
                value={tipo}
                onChange={(event) => setTipo(event.target.value)}
              >
                {TIPOS.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Origen
              <input
                value={origen}
                placeholder="Ej. consulta"
                maxLength={40}
                onChange={(event) => setOrigen(event.target.value)}
              />
            </label>
            <label>
              Archivo (imagen o PDF)
              <input
                key={fileKey}
                type="file"
                accept=".pdf,.jpg,.jpeg,.png,.webp"
                onChange={(event) =>
                  setArchivo(event.target.files?.[0] ?? null)
                }
              />
            </label>
            <div className="ficha-actions">
              <button
                type="button"
                disabled={saving}
                onClick={() => void submitAdjunto()}
              >
                Subir adjunto
              </button>
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
