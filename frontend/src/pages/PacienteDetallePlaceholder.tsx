import { useParams } from "react-router-dom";

/**
 * Placeholder de Detalle de paciente — contrato congelado para C-12/C-15.
 * - path: /pacientes/:id
 * - roles: propietario, odontologo, recepcion, asistente
 * - params: id (string de ruta, se muestra tal cual)
 * Datos ficticios. El change dueño reemplaza el contenido reutilizando `:id`.
 */
export default function PacienteDetallePlaceholder(): JSX.Element {
  const { id } = useParams();
  return (
    <section aria-labelledby="paciente-detalle-title">
      <h1 id="paciente-detalle-title">Paciente {id} (ficticio, contenido en su change)</h1>
      <p>El contenido del detalle llega en su change.</p>
    </section>
  );
}
