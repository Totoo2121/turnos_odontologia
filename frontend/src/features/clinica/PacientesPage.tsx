import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Table, type TableRow } from "../../shared/ui/Table";
import { listPacientes, mensajeError, type Paciente } from "./clinica-api";
import "./clinica.css";
import { NuevoPacienteForm } from "./NuevoPacienteForm";

const PAGE_SIZE = 20;

/** C-15: patient search with pagination and ficha navigation. */
export function PacientesPage(): JSX.Element {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [pacientes, setPacientes] = useState<Paciente[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<Paciente | null>(null);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    listPacientes(q, PAGE_SIZE, offset)
      .then((rows) => {
        if (active) {
          setPacientes(rows);
        }
      })
      .catch((cause: unknown) => {
        if (active) {
          setPacientes([]);
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
  }, [q, offset, revision]);

  const rows: TableRow[] = pacientes.map((paciente) => ({
    id: paciente.id,
    nombre: paciente.nombre,
    dni: paciente.dni ?? "—",
    telefono: paciente.telefono,
    obra_social: paciente.obra_social ?? "—",
  }));

  return (
    <section aria-labelledby="pacientes-title" className="clinica-page">
      <header className="clinica-header">
        <div>
          <h1 id="pacientes-title">Pacientes</h1>
          <p>Buscá por nombre o DNI y abrí la ficha del paciente.</p>
        </div>
        <button type="button" disabled={creating} onClick={() => { setCreating(true); setCreated(null); }}>Nuevo paciente</button>
      </header>

      {creating ? <NuevoPacienteForm onCancel={() => setCreating(false)} onCreated={(paciente) => {
        setCreating(false);
        setCreated(paciente);
        setQ(paciente.nombre);
        setOffset(0);
        setRevision((value) => value + 1);
      }} /> : null}
      {created ? <div className="clinica-success" role="status">
        Paciente creado correctamente. <button type="button" onClick={() => navigate(`/pacientes/${created.id}`)}>Abrir ficha de {created.nombre}</button>
      </div> : null}

      <div className="clinica-toolbar">
        <label htmlFor="pacientes-q">Buscar paciente</label>
        <input
          id="pacientes-q"
          type="search"
          value={q}
          placeholder="Nombre o DNI ficticio"
          onChange={(event) => {
            setQ(event.target.value);
            setOffset(0);
          }}
        />
      </div>

      {error !== null ? (
        <p role="alert" className="clinica-error">
          {error}
        </p>
      ) : null}
      {loading ? <p role="status">Cargando pacientes…</p> : null}

      <Table
        columns={[
          { key: "nombre", header: "Paciente" },
          { key: "dni", header: "DNI" },
          { key: "telefono", header: "Teléfono" },
          { key: "obra_social", header: "Obra social" },
          {
            key: "ficha",
            header: "",
            render: (row) => (
              <button
                type="button"
                onClick={() => navigate(`/pacientes/${row.id}`)}
              >
                Abrir ficha
              </button>
            ),
          },
        ]}
        rows={rows}
        emptyText={
          q.trim().length > 0
            ? "No hay pacientes que coincidan con la búsqueda."
            : "Todavía no hay pacientes cargados."
        }
      />

      <nav className="clinica-pager" aria-label="Paginación de pacientes">
        <button
          type="button"
          disabled={offset === 0 || loading}
          onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
        >
          Anterior
        </button>
        <span>Página {Math.floor(offset / PAGE_SIZE) + 1}</span>
        <button
          type="button"
          disabled={pacientes.length < PAGE_SIZE || loading}
          onClick={() => setOffset(offset + PAGE_SIZE)}
        >
          Siguiente
        </button>
      </nav>
    </section>
  );
}
