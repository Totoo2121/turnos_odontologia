/**
 * Placeholder de Pacientes — contrato congelado para su change de contenido.
 * - path: /pacientes
 * - roles: propietario, odontologo, recepcion, asistente
 * - params: ninguno
 * Datos ficticios. El change dueño reemplaza el contenido respetando path y guards.
 */
export default function PacientesPlaceholder(): JSX.Element {
  return (
    <section aria-labelledby="pacientes-title">
      <h1 id="pacientes-title">Pacientes (ficticio, contenido en su change)</h1>
      <p>El contenido de pacientes llega en su change.</p>
    </section>
  );
}
