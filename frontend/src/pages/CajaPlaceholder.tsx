/**
 * Placeholder de Caja — contrato congelado para C-15.
 * - path: /caja
 * - roles: propietario, recepcion, odontologo (solo lectura; el cobro lo cierra C-15)
 * - params: ninguno
 * Datos ficticios. C-15 reemplaza el contenido respetando path y guards.
 */
export default function CajaPlaceholder(): JSX.Element {
  return (
    <section aria-labelledby="caja-title">
      <h1 id="caja-title">Caja (ficticio, contenido en C-15)</h1>
      <p>El contenido de caja llega en su change.</p>
    </section>
  );
}
