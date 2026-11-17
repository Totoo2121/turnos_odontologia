import { useEffect, useState } from "react";
import { formatDateTime, formatMoney } from "../../shared/format";
import {
  aceptarPresupuesto,
  crearPresupuesto,
  enviarPresupuesto,
  getCuentaCorriente,
  getPlan,
  listPrestaciones,
  listPresupuestos,
  mensajeError,
  rechazarPresupuesto,
  type ItemPresupuestoInput,
  type PlanTratamiento,
  type Prestacion,
  type Presupuesto,
  type Superficie,
} from "./clinica-api";

interface PresupuestosTabProps {
  pacienteId: string;
  historiaId: string;
  canWrite: boolean;
}

interface DraftItem extends ItemPresupuestoInput {
  key: number;
}

const SUPERFICIES: Superficie[] = [
  "oclusal",
  "mesial",
  "distal",
  "vestibular",
  "lingual",
  "palatina",
  "incisal",
];

function estadoLabel(estado: string): string {
  return estado.charAt(0).toUpperCase() + estado.slice(1);
}

/** C-15 budget builder, lifecycle actions and generated treatment plan. */
export function PresupuestosTab({
  pacienteId,
  historiaId,
  canWrite,
}: PresupuestosTabProps): JSX.Element {
  const [presupuestos, setPresupuestos] = useState<Presupuesto[]>([]);
  const [prestaciones, setPrestaciones] = useState<Prestacion[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const [items, setItems] = useState<DraftItem[]>([]);
  const [prestacionId, setPrestacionId] = useState("");
  const [cantidad, setCantidad] = useState("1");
  const [etapa, setEtapa] = useState("1");
  const [pieza, setPieza] = useState("");
  const [superficie, setSuperficie] = useState<Superficie | "">("");
  const [observaciones, setObservaciones] = useState("");
  const [saving, setSaving] = useState(false);
  const [nextKey, setNextKey] = useState(1);

  const [plan, setPlan] = useState<PlanTratamiento | null>(null);
  const [saldo, setSaldo] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadError(null);
    Promise.all([listPresupuestos(pacienteId), listPrestaciones()])
      .then(([rows, catalogo]) => {
        if (active) {
          setPresupuestos(rows);
          setPrestaciones(catalogo.filter((item) => item.is_active));
        }
      })
      .catch((cause: unknown) => {
        if (active) {
          setPresupuestos([]);
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

  async function refrescar(): Promise<void> {
    try {
      const rows = await listPresupuestos(pacienteId);
      setPresupuestos(rows);
    } catch (cause: unknown) {
      setError(mensajeError(cause));
    }
  }

  function prestacionNombre(id: string): string {
    return prestaciones.find((item) => item.id === id)?.nombre ?? id;
  }

  function agregarItem(): void {
    setError(null);
    setAviso(null);
    if (prestacionId === "") {
      setError("Elegí una prestación para el ítem.");
      return;
    }
    const cantidadNum = Number(cantidad);
    const etapaNum = Number(etapa);
    if (!Number.isInteger(cantidadNum) || cantidadNum < 1) {
      setError("La cantidad debe ser un entero mayor o igual a 1.");
      return;
    }
    if (!Number.isInteger(etapaNum) || etapaNum < 1) {
      setError("La etapa debe ser un entero mayor o igual a 1.");
      return;
    }
    const piezaNum = pieza === "" ? null : Number(pieza);
    if (piezaNum !== null && (!Number.isInteger(piezaNum) || piezaNum < 11 || piezaNum > 48)) {
      setError("La pieza FDI debe estar entre 11 y 48.");
      return;
    }
    setItems((prev) => [
      ...prev,
      {
        key: nextKey,
        prestacion_id: prestacionId,
        cantidad: cantidadNum,
        etapa: etapaNum,
        pieza_fdi: piezaNum,
        superficie: piezaNum === null ? null : superficie === "" ? null : superficie,
      },
    ]);
    setNextKey((prev) => prev + 1);
    setPrestacionId("");
    setCantidad("1");
    setPieza("");
    setSuperficie("");
  }

  function quitarItem(key: number): void {
    setItems((prev) => prev.filter((item) => item.key !== key));
  }

  async function guardarPresupuesto(): Promise<void> {
    if (items.length === 0) {
      setError("Agregá al menos un ítem al presupuesto.");
      return;
    }
    setSaving(true);
    setError(null);
    setAviso(null);
    try {
      const creado = await crearPresupuesto({
        paciente_id: pacienteId,
        historia_clinica_id: historiaId,
        observaciones:
          observaciones.trim().length === 0 ? null : observaciones.trim(),
        items: items.map((item) => ({
          prestacion_id: item.prestacion_id,
          cantidad: item.cantidad,
          etapa: item.etapa,
          pieza_fdi: item.pieza_fdi,
          superficie: item.superficie,
        })),
      });
      setPresupuestos((prev) => [creado, ...prev]);
      setItems([]);
      setObservaciones("");
      setAviso(
        `Presupuesto guardado en borrador por ${formatMoney(creado.total)}.`,
      );
    } catch (cause: unknown) {
      setError(mensajeError(cause));
    } finally {
      setSaving(false);
    }
  }

  async function ejecutarAccion(
    presupuestoId: string,
    accion: "enviar" | "aceptar" | "rechazar",
  ): Promise<void> {
    setBusyId(presupuestoId);
    setError(null);
    setAviso(null);
    try {
      if (accion === "enviar") {
        const actualizado = await enviarPresupuesto(presupuestoId);
        setPresupuestos((prev) =>
          prev.map((item) => (item.id === actualizado.id ? actualizado : item)),
        );
        setAviso("Presupuesto enviado al paciente.");
        return;
      }
      if (accion === "rechazar") {
        const actualizado = await rechazarPresupuesto(presupuestoId);
        setPresupuestos((prev) =>
          prev.map((item) => (item.id === actualizado.id ? actualizado : item)),
        );
        setAviso("Presupuesto rechazado.");
        return;
      }
      const aceptado = await aceptarPresupuesto(presupuestoId);
      setPresupuestos((prev) =>
        prev.map((item) => (item.id === aceptado.id ? aceptado : item)),
      );
      setAviso("Presupuesto aceptado. Plan y deuda registrados.");
      if (aceptado.plan_id !== null) {
        try {
          const [planGenerado, cuenta] = await Promise.all([
            getPlan(aceptado.plan_id),
            getCuentaCorriente(pacienteId),
          ]);
          setPlan(planGenerado);
          setSaldo(cuenta.saldo);
        } catch {
          // The acceptance already succeeded; follow-up reads are best effort.
          setPlan(null);
          setSaldo(null);
        }
      }
    } catch (cause: unknown) {
      setError(mensajeError(cause));
      // Domain conflicts (409) refresh so the UI shows the current state.
      await refrescar();
    } finally {
      setBusyId(null);
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

      {plan !== null ? (
        <section className="ficha-card" aria-labelledby="plan-title">
          <h2 id="plan-title">Plan de tratamiento generado</h2>
          <div className="ficha-meta">
            <span>Estado: {plan.estado}</span>
            <span>Etapas: {plan.etapas}</span>
            <span>Total: {formatMoney(plan.total)}</span>
            {saldo !== null ? <span>Saldo: {formatMoney(saldo)}</span> : null}
          </div>
          <ul className="ficha-list">
            {plan.detalle.map((etapaPlan) => (
              <li key={etapaPlan.etapa} className="ficha-list-item">
                <strong>Etapa {etapaPlan.etapa}</strong> —{" "}
                {formatMoney(etapaPlan.subtotal)}
                <ul>
                  {etapaPlan.items.map((item) => (
                    <li key={item.id}>
                      {item.descripcion} × {item.cantidad} —{" "}
                      {formatMoney(item.importe)}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
          <p className="clinica-muted">
            La deuda quedó registrada en la cuenta corriente del paciente.
          </p>
        </section>
      ) : null}

      {canWrite ? (
        <section className="ficha-card" aria-labelledby="nuevo-presupuesto-title">
          <h2 id="nuevo-presupuesto-title">Nuevo presupuesto</h2>
          <div className="ficha-grid-2">
            <label>
              Prestación
              <select
                value={prestacionId}
                onChange={(event) => setPrestacionId(event.target.value)}
              >
                <option value="">Elegir prestación</option>
                {prestaciones.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.nombre}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Cantidad
              <input
                type="number"
                min={1}
                max={999}
                value={cantidad}
                onChange={(event) => setCantidad(event.target.value)}
              />
            </label>
            <label>
              Etapa
              <input
                type="number"
                min={1}
                max={20}
                value={etapa}
                onChange={(event) => setEtapa(event.target.value)}
              />
            </label>
            <label>
              Pieza FDI (opcional)
              <input
                type="number"
                min={11}
                max={48}
                value={pieza}
                onChange={(event) => setPieza(event.target.value)}
              />
            </label>
            <label>
              Superficie (opcional)
              <select
                value={superficie}
                disabled={pieza === ""}
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
            </label>
          </div>
          <div className="ficha-actions">
            <button type="button" onClick={agregarItem}>
              Agregar ítem
            </button>
          </div>

          {items.length > 0 ? (
            <ul className="ficha-list">
              {items.map((item) => (
                <li key={item.key} className="ficha-list-item">
                  <div className="ficha-meta">
                    <strong>{prestacionNombre(item.prestacion_id)}</strong>
                    <span>Cantidad: {item.cantidad}</span>
                    <span>Etapa: {item.etapa}</span>
                    {item.pieza_fdi !== null ? (
                      <span>
                        Pieza {item.pieza_fdi}
                        {item.superficie !== null
                          ? ` (${item.superficie})`
                          : ""}
                      </span>
                    ) : null}
                  </div>
                  <button type="button" onClick={() => quitarItem(item.key)}>
                    Quitar ítem
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="ficha-empty">El presupuesto todavía no tiene ítems.</p>
          )}

          <div className="ficha-field">
            <label htmlFor="presupuesto-observaciones">Observaciones</label>
            <textarea
              id="presupuesto-observaciones"
              value={observaciones}
              maxLength={2000}
              onChange={(event) => setObservaciones(event.target.value)}
            />
          </div>
          <div className="ficha-actions">
            <button
              type="button"
              disabled={saving}
              onClick={() => void guardarPresupuesto()}
            >
              Guardar presupuesto
            </button>
          </div>
          <p className="clinica-muted">
            El total lo calcula el servidor con los precios del catálogo.
          </p>
        </section>
      ) : null}

      <section className="ficha-card" aria-labelledby="presupuestos-title">
        <h2 id="presupuestos-title">Presupuestos del paciente</h2>
        {loading ? <p role="status">Cargando presupuestos…</p> : null}
        {loadError !== null ? (
          <p role="alert" className="clinica-error">
            {loadError}
          </p>
        ) : null}
        {!loading && loadError === null && presupuestos.length === 0 ? (
          <p className="ficha-empty">Todavía no hay presupuestos.</p>
        ) : null}
        {presupuestos.length > 0 ? (
          <ul className="ficha-list">
            {presupuestos.map((presupuesto) => (
              <li key={presupuesto.id} className="ficha-list-item">
                <div className="ficha-meta">
                  <span
                    className="ficha-badge"
                    data-estado={presupuesto.estado}
                  >
                    {estadoLabel(presupuesto.estado)}
                  </span>
                  <strong>{formatMoney(presupuesto.total)}</strong>
                  <span>{presupuesto.items.length} ítems</span>
                  <span>Creado: {formatDateTime(presupuesto.created_at)}</span>
                </div>
                {presupuesto.observaciones !== null ? (
                  <p>{presupuesto.observaciones}</p>
                ) : null}
                <ul>
                  {presupuesto.items.map((item) => (
                    <li key={item.id}>
                      {item.descripcion} × {item.cantidad} —{" "}
                      {formatMoney(item.importe)}
                      {item.etapa > 1 ? ` (etapa ${item.etapa})` : ""}
                    </li>
                  ))}
                </ul>
                {canWrite ? (
                  <div className="ficha-actions">
                    {presupuesto.estado === "borrador" ? (
                      <button
                        type="button"
                        disabled={busyId === presupuesto.id}
                        onClick={() =>
                          void ejecutarAccion(presupuesto.id, "enviar")
                        }
                      >
                        Enviar presupuesto
                      </button>
                    ) : null}
                    {presupuesto.estado === "enviado" ? (
                      <>
                        <button
                          type="button"
                          disabled={busyId === presupuesto.id}
                          onClick={() =>
                            void ejecutarAccion(presupuesto.id, "aceptar")
                          }
                        >
                          Aceptar presupuesto
                        </button>
                        <button
                          type="button"
                          disabled={busyId === presupuesto.id}
                          onClick={() =>
                            void ejecutarAccion(presupuesto.id, "rechazar")
                          }
                        >
                          Rechazar presupuesto
                        </button>
                      </>
                    ) : null}
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </div>
  );
}
