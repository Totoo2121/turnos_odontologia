import { Outlet } from "react-router-dom";
import "./AuthLayout.css";

/** Layout minimal de autenticación: marca + contenido, sin navegación privada. */
export function AuthLayout(): JSX.Element {
  return (
    <div className="auth-layout">
      <header className="auth-layout-brand">
        <span>Turnos Odontología</span>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}
