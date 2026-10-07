import { Link } from "react-router-dom";

/** 404: ruta desconocida; se renderiza dentro del layout que corresponda a la sesión. */
export function NotFound(): JSX.Element {
  return (
    <section aria-labelledby="notfound-title">
      <h1 id="notfound-title">404 — Página no encontrada</h1>
      <p>La ruta que buscás no existe.</p>
      <Link to="/agenda">Volver a la agenda</Link>
    </section>
  );
}
