import { useEffect, useState } from "react";
import { useAuthStore, type Role } from "../auth/auth-store";
import { canCharge } from "../../shared/permissions";
import {
  formatDateTime,
  formatMoney,
  shortId,
  todayIso,
} from "../../shared/format";
import {
  abrirBlob,
  getPaciente,
  listPacientes,
  mensajeError,
  type Paciente,
} from "../clinica/clinica-api";
import {
  MEDIOS_PAGO,
  descargarRecibo,
  getCierre,
  getCuenta,
  listTurnosDia,
  medioLabel,
  nuevaClaveIdempotencia,
  parseMedioPago,
  registrarPago,
  type CierreCaja,
  type CuentaCorriente,
  type MedioPago,
  type MovimientoCC,
  type TurnoCaja,
} from "./caja-api";
import "../clinica/clinica.css";

const EMPTY_ROLES: Role[] = [];

function estadoLabel(estado: string): string {
  return estado.charAt(0).toUpperCase() + estado.slice(1);
}

function cobroLabel(cobro: string): string {
  if (cobro === "sin-sena") {
    return "Sin seña";
  }
  if (cobro === "acreditado") {
    return "Acreditado";
  }
  return estadoLabel(cobro);
}

function hora(iso: string): string {
  return formatDateTime(iso).split(", ")[1] ?? formatDateTime(iso);
}

/**
 * C-15 counter cash: patient balance, manual payments (cash/transfer/MP),
 * receipts and the daily close against attended appointments. The role matrix
 * is enforced by the route guard and repeated here for the payment form.
 */
export function CajaPage(): JSX.Element {
  const user = useAuthStore((state) => state.user);
  const roles = user?.roles ?? EMPTY_ROLES;
  const canCollect = canCharge(roles);

  const [q, setQ] = useState("");
  const [resultados, setResultados] = useState<Paciente[]>([]);
  const [buscando, setBuscando] = useState(false);
  const [paciente, setPaciente] = useState<Paciente | null>(null);
  const [cuenta, setCuenta] = useState<CuentaCorriente | null>(null);
  const [loadingCuenta, setLoadingCuenta] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const [monto, setMonto] = useState("");
  const [medio, setMedio] = useState<MedioPago>("efectivo");
  const [descripcion, setDescripcion] = useState("");
  const [clave, setClave] = useState(nuevaClaveIdempotencia);
  const [cobrando, setCobrando] = useState(false);
  const [descargandoId, setDescargandoId] = useState<string | null>(null);

  const [fecha, setFecha] = useState(todayIso());
  const [cierre, setCierre] = useState<CierreCaja | null>(null);
  const [turnos, setTurnos] = useState<TurnoCaja[]>([]);
  const [loadingCierre, setLoadingCierre] = useState(true);
  const [cierreError, setCierreError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoadingCierre(true);
    setCierreError(null);
    Promise.all([getCierre(fecha), listTurnosDia(fecha)])
      .then(([cierreData, turnosData]) => {
        if (!active) {
          return;
        }
        setCierre(cierreData);
        setTurnos(turnosData);
      })
      .catch((cause: unknown) => {
        if (active) {
          setCierre(null);
          setTurnos([]);
          setCierreError(mensajeError(cause));
        }
      })
      .finally(() => {
        if (active) {
          setLoadingCierre(false);
        }
      });
    return () => {
      active = false;
    };
  }, [fecha]);

  async function buscar(): Promise<void> {
    setBuscando(true);
    setError(null);
    setAviso(null);
    try {
      const rows = await listPacientes(q, 10);
      setResultados(rows);
    } catch (cause: unknown) {
      setResultados([]);
      setError(mensajeError(cause));
    } finally {
      setBuscando(false);
    }
  }

  async function verCuenta(target: Paciente): Promise<void> {
    setPaciente(target);
    setCuenta(null);
    setLoadingCuenta(true);
    setError(null);
    setAviso(null);
    setClave(nuevaClaveIdempotencia());
    try {
      setCuenta(await getCuenta(target.id));
    } catch (cause: unknown) {
      setError(mensajeError(cause));
    } finally {
      setLoadingCuenta(false);
    }
  }

  async function verCuentaPorId(pacienteId: string): Promise<void> {
    setError(null);
    try {
      const target = await getPaciente(pacienteId);
      await verCuenta(target);
    } catch (cause: unknown) {
      setError(mensajeError(cause));
    }
  }

  async function cobrar(): Promise<void> {
    if (paciente === null || cuenta === null) {
      return;
    }
    const montoNum = Number(monto);
    if (!Number.isFinite(montoNum) || montoNum <= 0) {
      setError("El monto debe ser mayor a cero.");
      return;
    }
    setCobrando(true);
    setError(null);
    setAviso(null);
    try {
      const pago = await registrarPago(paciente.id, {
        monto: montoNum,
        medio,
        idempotency_key: clave,
        descripcion:
          descripcion.trim().length === 0 ? null : descripcion.trim(),
      });
      setCuenta({
        ...cuenta,
        saldo: pago.saldo,
        movimientos: [pago.movimiento, ...cuenta.movimientos],
      });
      setMonto("");
      setDescripcion("");
      setClave(nuevaClaveIdempotencia());
      setAviso(
        `Cobro registrado con ${medioLabel(pago.medio)}. Saldo actualizado: ${formatMoney(pago.saldo)}.`,
      );
      getCierre(fecha)
        .then(setCierre)
        .catch(() => {
          // The payment already succeeded; refreshing the close is best effort.
        });
    } catch (cause: unknown) {
      // Keep the idempotency key so a retry cannot duplicate the credit.
      setError(mensajeError(cause));
    } finally {
      setCobrando(false);
    }
  }

  async function bajarRecibo(movimiento: MovimientoCC): Promise<void> {
    setDescargandoId(movimiento.id);
    setError(null);
    try {
      const blob = await descargarRecibo(movimiento.id);
      abrirBlob(blob, `recibo-${shortId(movimiento.id)}.pdf`);
    } catch (cause: unknown) {
      setError(mensajeError(cause));
    } finally {
      setDescargandoId(null);
    }
  }

  return (
    <section aria-labelledby="caja-title" className="clinica-page">
      <header className="clinica-header">
        <div>
          <h1 id="caja-title">Caja</h1>
          <p>
            Deuda del paciente, cobros manuales en efectivo, transferencia o
            Mercado Pago, recibos y cierre del día.
          </p>
        </div>
      </header>

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

      <section className="ficha-card" aria-labelledby="caja-buscar-title">
        <h2 id="caja-buscar-title">Buscar paciente</h2>
        <form
          className="clinica-toolbar"
          onSubmit={(event) => {
            event.preventDefault();
            void buscar();
          }}
        >
          <label htmlFor="caja-q">Buscar paciente</label>
          <input
            id="caja-q"
            type="search"
            value={q}
            placeholder="Nombre o DNI ficticio"
            onChange={(event) => setQ(event.target.value)}
          />
          <button type="submit" disabled={buscando}>
            Buscar
          </button>
        </form>
        {buscando ? <p role="status">Buscando pacientes…</p> : null}
        {!buscando && resultados.length === 0 ? (
          <p className="ficha-empty">
            No hay pacientes que coincidan con la búsqueda.
          </p>
        ) : null}
        {resultados.length > 0 ? (
          <ul className="ficha-list">
            {resultados.map((item) => (
              <li key={item.id} className="ficha-list-item">
                <div className="ficha-meta">
                  <strong>{item.nombre}</strong>
                  <span>DNI: {item.dni ?? "—"}</span>
                  <span>Teléfono: {item.telefono}</span>
                </div>
                <button
                  type="button"
                  onClick={() => void verCuenta(item)}
                >
                  Ver cuenta
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      {loadingCuenta ? <p role="status">Cargando cuenta corriente…</p> : null}

      {paciente !== null && cuenta !== null ? (
        <section className="ficha-card" aria-labelledby="caja-cuenta-title">
          <h2 id="caja-cuenta-title">
            Cuenta corriente de {paciente.nombre}
          </h2>
          <div className="caja-saldo">
            <span>Saldo</span>
            <strong>{formatMoney(cuenta.saldo)}</strong>
            <span>{cuenta.moneda}</span>
          </div>

          {cuenta.movimientos.length === 0 ? (
            <p className="ficha-empty">
              El paciente no tiene movimientos en su cuenta corriente.
            </p>
          ) : (
            <ul className="ficha-list">
              {cuenta.movimientos.map((movimiento) => (
                <li key={movimiento.id} className="ficha-list-item">
                  <div className="ficha-meta">
                    <span
                      className="ficha-badge"
                      data-tone={
                        movimiento.tipo === "credito" ? "ok" : undefined
                      }
                    >
                      {estadoLabel(movimiento.tipo)}
                    </span>
                    <strong>{formatMoney(movimiento.monto)}</strong>
                    <span>{movimiento.descripcion}</span>
                    {movimiento.ocurrido_at ? (
                      <span>{formatDateTime(movimiento.ocurrido_at)}</span>
                    ) : null}
                  </div>
                  {movimiento.referencia !== null ? (
                    <p className="clinica-muted">
                      Referencia: {movimiento.referencia}
                    </p>
                  ) : null}
                  {parseMedioPago(movimiento.referencia) !== null ? (
                    <button
                      type="button"
                      disabled={descargandoId === movimiento.id}
                      onClick={() => void bajarRecibo(movimiento)}
                    >
                      Descargar recibo
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}

      {paciente !== null && cuenta !== null && canCollect ? (
        <section className="ficha-card" aria-labelledby="caja-cobro-title">
          <h2 id="caja-cobro-title">Registrar cobro</h2>
          <div className="ficha-grid-2">
            <label>
              Monto
              <input
                type="number"
                min={0}
                step="0.01"
                value={monto}
                onChange={(event) => setMonto(event.target.value)}
              />
            </label>
            <label>
              Medio de pago
              <select
                value={medio}
                onChange={(event) =>
                  setMedio(event.target.value as MedioPago)
                }
              >
                {MEDIOS_PAGO.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Descripción (opcional)
              <input
                value={descripcion}
                maxLength={200}
                placeholder="Ej. saldo de obturación"
                onChange={(event) => setDescripcion(event.target.value)}
              />
            </label>
          </div>
          <p className="clinica-muted">
            Clave de idempotencia: {clave}
          </p>
          <div className="ficha-actions">
            <button
              type="button"
              disabled={cobrando}
              onClick={() => void cobrar()}
            >
              Registrar cobro
            </button>
          </div>
        </section>
      ) : null}

      {paciente !== null && cuenta !== null && !canCollect ? (
        <p className="clinica-notice">
          Podés consultar la caja y descargar recibos, pero tu rol no registra
          cobros.
        </p>
      ) : null}

      <section className="ficha-card" aria-labelledby="caja-cierre-title">
        <h2 id="caja-cierre-title">Cierre de caja</h2>
        <div className="clinica-toolbar">
          <label htmlFor="caja-fecha">Fecha del cierre</label>
          <input
            id="caja-fecha"
            type="date"
            value={fecha}
            onChange={(event) => setFecha(event.target.value)}
          />
        </div>

        {loadingCierre ? <p role="status">Cargando cierre…</p> : null}
        {cierreError !== null ? (
          <p role="alert" className="clinica-error">
            {cierreError}
          </p>
        ) : null}

        {cierre !== null ? (
          <>
            <dl className="caja-grid">
              <div className="caja-total">
                <dt>Cobrado</dt>
                <dd>{formatMoney(cierre.cobrado_total)}</dd>
              </div>
              <div className="caja-total">
                <dt>Pagos</dt>
                <dd>{cierre.cantidad_pagos}</dd>
              </div>
              <div className="caja-total">
                <dt>Deuda generada</dt>
                <dd>{formatMoney(cierre.deuda_generada)}</dd>
              </div>
              <div className="caja-total">
                <dt>Diferencia de caja</dt>
                <dd>{formatMoney(cierre.diferencia_caja)}</dd>
              </div>
              <div className="caja-total">
                <dt>Turnos atendidos</dt>
                <dd>{cierre.turnos_atendidos}</dd>
              </div>
            </dl>

            <h3>Cobrado por medio</h3>
            <dl className="caja-grid">
              {MEDIOS_PAGO.map((item) => (
                <div key={item.value} className="caja-total">
                  <dt>{item.label}</dt>
                  <dd>{formatMoney(cierre.por_medio[item.value] ?? "0")}</dd>
                </div>
              ))}
            </dl>

            <h3>Movimientos del día</h3>
            {cierre.movimientos.length === 0 ? (
              <p className="ficha-empty">
                No hay movimientos registrados para la fecha.
              </p>
            ) : (
              <ul className="ficha-list">
                {cierre.movimientos.map((movimiento) => (
                  <li key={movimiento.id} className="ficha-list-item">
                    <div className="ficha-meta">
                      <span>{estadoLabel(movimiento.tipo)}</span>
                      <strong>{formatMoney(movimiento.monto)}</strong>
                      <span>{movimiento.descripcion}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : null}

        <h3>Turnos del día</h3>
        {turnos.length === 0 ? (
          <p className="ficha-empty">
            No hay turnos agendados para la fecha.
          </p>
        ) : (
          <ul className="ficha-list">
            {turnos.map((turno) => (
              <li key={turno.id} className="ficha-list-item">
                <div className="ficha-meta">
                  <strong>{hora(turno.inicio)}</strong>
                  <span className="ficha-badge">{estadoLabel(turno.estado)}</span>
                  <span
                    className="ficha-badge"
                    data-tone={turno.cobro === "acreditado" ? "ok" : undefined}
                  >
                    Cobro: {cobroLabel(turno.cobro)}
                  </span>
                  {turno.cobro_monto !== null ? (
                    <span>{formatMoney(turno.cobro_monto)}</span>
                  ) : null}
                </div>
                {turno.paciente_id !== null ? (
                  <button
                    type="button"
                    onClick={() => void verCuentaPorId(turno.paciente_id as string)}
                  >
                    Ver cuenta del turno
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}
