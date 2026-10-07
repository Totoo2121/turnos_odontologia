/**
 * Placeholder de Admin — contrato congelado para su change de contenido.
 * - path: /admin
 * - roles: solo propietario
 * - params: ninguno
 * Datos ficticios. El change dueño reemplaza el contenido respetando path y guards.
 */
export default function AdminPlaceholder(): JSX.Element {
  return (
    <section aria-labelledby="admin-title">
      <h1 id="admin-title">Admin (ficticio, contenido en su change)</h1>
      <p>El contenido de administración llega en su change.</p>
    </section>
  );
}
