import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { routesForRoles } from "./guards";
import { useAuthStore } from "../features/auth/auth-store";
import "./AppShell.css";

/** Shell de rutas privadas: header (usuario + logout), nav filtrada por rol, outlet. */
export function AppShell(): JSX.Element {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const routes = routesForRoles(user?.roles ?? []);

  async function handleLogout(): Promise<void> {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="shell">
      <header className="shell-header">
        <button
          type="button"
          className="shell-menu-button"
          aria-label="Menú"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
        >
          ☰
        </button>
        <span className="shell-brand">Turnos Odontología</span>
        <span className="shell-user">{user !== null ? user.email : ""}</span>
        <button type="button" onClick={() => void handleLogout()}>
          Cerrar sesión
        </button>
      </header>
      <nav aria-label="Principal" data-open={menuOpen ? "true" : "false"} className="shell-nav">
        <ul>
          {routes.map((route) => (
            <li key={route.key}>
              <NavLink to={route.path} onClick={() => setMenuOpen(false)}>
                {route.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <main className="shell-main">
        <Outlet />
      </main>
    </div>
  );
}
