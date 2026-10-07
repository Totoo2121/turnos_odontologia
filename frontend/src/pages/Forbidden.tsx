import { Link } from "react-router-dom";

/** 403: rol autenticado sin permiso para la ruta. */
export function Forbidden(): JSX.Element {
  return (
    <section aria-labelledby="forbidden-title">
      <h1 id="forbidden-title">403 — Sin permiso</h1>
      <p>Tu rol no tiene acceso a esta sección.</p>
      <Link to="/agenda">Volver a la agenda</Link>
    </section>
  );
}
