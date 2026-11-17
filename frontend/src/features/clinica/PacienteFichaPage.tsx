import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuthStore, type Role } from "../auth/auth-store";
import {
  canAccessClinical,
  canCreateAgenda,
  canWriteAgenda,
  canWriteClinical,
} from "../../shared/permissions";
import { ApiError } from "../../shared/api-client";
import { formatDate } from "../../shared/format";
import {
  abrirHistoria,
  getPaciente,
  mensajeError,
  type Historia,
  type Paciente,
} from "./clinica-api";
import { HceTab } from "./HceTab";
import { OdontogramaTab } from "./OdontogramaTab";
import { AdjuntosTab } from "./AdjuntosTab";
import { PresupuestosTab } from "./PresupuestosTab";
import { ConsentimientosTab } from "./ConsentimientosTab";
import { TurnoPanel } from "./TurnoPanel";
import "./clinica.css";

const EMPTY_ROLES: Role[] = [];

type TabKey = "hce" | "odontograma" | "adjuntos" | "presupuestos" | "consentimientos";
type ClinicalStatus = "idle" | "loading" | "ready" | "denied" | "error";

const TABS: { key: TabKey; label: string }[] = [
  { key: "hce", label: "HCE" },
  { key: "odontograma", label: "Odontograma" },
  { key: "adjuntos", label: "Adjuntos" },
  { key: "presupuestos", label: "Presupuestos" },
  { key: "consentimientos", label: "Consentimientos" },
];

/** C-15 patient ficha: administrative block plus role-gated clinical tabs. */
export function PacienteFichaPage(): JSX.Element {
  const { id = "" } = useParams<{ id: string }>();
  const user = useAuthStore((state) => state.user);
  const roles = user?.roles ?? EMPTY_ROLES;

  const [paciente, setPaciente] = useState<Paciente | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [historia, setHistoria] = useState<Historia | null>(null);
  const [clinicalStatus, setClinicalStatus] = useState<ClinicalStatus>("idle");
  const [clinicalError, setClinicalError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>("hce");

  const clinical = canAccessClinical(roles);
  const writeClinical = canWriteClinical(roles);
  const closeTurn = canWriteAgenda(roles);
  const scheduleControl = canCreateAgenda(roles);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getPaciente(id)
      .then((data) => {
        if (active) {
          setPaciente(data);
        }
      })
      .catch((cause: unknown) => {
        if (active) {
          setPaciente(null);
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
  }, [id]);

  useEffect(() => {
    if (!clinical) {
      setHistoria(null);
      setClinicalStatus("idle");
      setClinicalError(null);
      return;
    }
    let active = true;
    setClinicalStatus("loading");
    setClinicalError(null);
    abrirHistoria(id)
      .then((data) => {
        if (active) {
          setHistoria(data);
          setClinicalStatus("ready");
        }
      })
      .catch((cause: unknown) => {
        if (!active) {
          return;
        }
        setHistoria(null);
        if (cause instanceof ApiError && cause.status === 403) {
          setClinicalStatus("denied");
        } else {
          setClinicalStatus("error");
          setClinicalError(mensajeError(cause));
        }
      });
    return () => {
      active = false;
    };
  }, [id, clinical]);

  if (loading) {
    return (
      <section className="clinica-page">
        <p role="status">Cargando ficha del paciente…</p>
      </section>
    );
  }

  if (paciente === null) {
    return (
      <section className="clinica-page">
        <p role="alert" className="clinica-error">
          {error ?? "No se encontró el paciente en este tenant."}
        </p>
        <Link to="/pacientes">Volver a pacientes</Link>
      </section>
    );
  }

  return (
    <section aria-labelledby="ficha-title" className="clinica-page">
      <header className="clinica-header">
        <div>
          <h1 id="ficha-title">{paciente.nombre}</h1>
          <p>Ficha del paciente</p>
        </div>
        <Link to="/pacientes">Volver a pacientes</Link>
      </header>

      <dl className="ficha-admin" aria-label="Datos administrativos">
        <div>
          <dt>DNI</dt>
          <dd>{paciente.dni ?? "—"}</dd>
        </div>
        <div>
          <dt>Teléfono</dt>
          <dd>{paciente.telefono}</dd>
        </div>
        <div>
          <dt>Email</dt>
          <dd>{paciente.email ?? "—"}</dd>
        </div>
        <div>
          <dt>Obra social</dt>
          <dd>{paciente.obra_social ?? "—"}</dd>
        </div>
        <div>
          <dt>Consentimiento de datos</dt>
          <dd>{paciente.consentimiento_datos ? "Sí" : "No"}</dd>
        </div>
        <div>
          <dt>Alta</dt>
          <dd>{formatDate(paciente.created_at)}</dd>
        </div>
      </dl>

      {closeTurn || scheduleControl ? (
        <TurnoPanel
          pacienteId={paciente.id}
          canClose={closeTurn}
          canSchedule={scheduleControl}
        />
      ) : null}

      {!clinical ? (
        <p className="clinica-notice">
          Los datos clínicos solo están disponibles para el odontólogo tratante
          y el propietario.
        </p>
      ) : null}

      {clinical && clinicalStatus === "loading" ? (
        <p role="status">Cargando historia clínica…</p>
      ) : null}

      {clinical && clinicalStatus === "denied" ? (
        <p role="alert" className="clinica-error">
          Acceso clínico restringido: no sos el profesional tratante ni tenés
          una derivación vigente para este paciente.
        </p>
      ) : null}

      {clinical && clinicalStatus === "error" ? (
        <p role="alert" className="clinica-error">
          {clinicalError ?? "No se pudo cargar la historia clínica."}
        </p>
      ) : null}

      {clinical && clinicalStatus === "ready" && historia !== null ? (
        <div className="ficha-panel">
          <div
            role="tablist"
            aria-label="Secciones clínicas"
            className="ficha-tabs"
          >
            {TABS.map((item) => (
              <button
                key={item.key}
                id={`tab-${item.key}`}
                type="button"
                role="tab"
                aria-selected={tab === item.key}
                aria-controls={`panel-${item.key}`}
                onClick={() => setTab(item.key)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div
            id={`panel-${tab}`}
            role="tabpanel"
            aria-labelledby={`tab-${tab}`}
          >
            {tab === "hce" ? (
              <HceTab historia={historia} canWrite={writeClinical} />
            ) : null}
            {tab === "odontograma" ? (
              <OdontogramaTab
                historiaId={historia.id}
                canWrite={writeClinical}
              />
            ) : null}
            {tab === "adjuntos" ? (
              <AdjuntosTab
                historiaId={historia.id}
                canWrite={writeClinical}
              />
            ) : null}
            {tab === "presupuestos" ? (
              <PresupuestosTab
                pacienteId={paciente.id}
                historiaId={historia.id}
                canWrite={writeClinical}
              />
            ) : null}
            {tab === "consentimientos" ? (
              <ConsentimientosTab
                pacienteId={paciente.id}
                historiaId={historia.id}
                canWrite={writeClinical}
              />
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
