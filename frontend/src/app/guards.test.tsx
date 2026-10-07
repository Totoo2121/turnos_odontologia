/** RED — task 3.1: guards como comportamiento rol×ruta. Datos 100% ficticios. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ROLE_ROUTES, RequireAuth, RequireRole } from "./guards";
import { useAuthStore, type Role } from "../features/auth/auth-store";

type Session = { roles: Role[] | null }; // null = anónimo

function presetSession(session: Session): void {
  if (session.roles === null) {
    useAuthStore.setState({
      accessToken: null,
      user: null,
      status: "unauthenticated",
      error: null,
    });
  } else {
    useAuthStore.setState({
      accessToken: "access-ficticio-g",
      user: {
        id: "u-ficticia-g",
        email: "alguien@ficticio.test",
        roles: session.roles,
        tenantId: "t-ficticio-1",
      },
      status: "authenticated",
      error: null,
    });
  }
}

function renderAt(path: string): void {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<p>Página de ingreso ficticia</p>} />
        <Route path="/403" element={<p>Sin permiso ficticio</p>} />
        <Route
          path="/agenda"
          element={
            <RequireAuth>
              <RequireRole allowed={ROLE_ROUTES.agenda}>
                <p>Agenda ficticia</p>
              </RequireRole>
            </RequireAuth>
          }
        />
        <Route
          path="/admin"
          element={
            <RequireAuth>
              <RequireRole allowed={ROLE_ROUTES.admin}>
                <p>Admin ficticio</p>
              </RequireRole>
            </RequireAuth>
          }
        />
        <Route
          path="/caja"
          element={
            <RequireAuth>
              <RequireRole allowed={ROLE_ROUTES.caja}>
                <p>Caja ficticia</p>
              </RequireRole>
            </RequireAuth>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("guards rol×ruta (RED 3.1)", () => {
  beforeEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("anónimo en ruta privada va a /login", () => {
    presetSession({ roles: null });
    renderAt("/agenda");
    expect(screen.getByText("Página de ingreso ficticia")).toBeInTheDocument();
    expect(screen.queryByText("Agenda ficticia")).not.toBeInTheDocument();
  });

  it("asistente en /admin ve 403", () => {
    presetSession({ roles: ["asistente"] });
    renderAt("/admin");
    expect(screen.getByText("Sin permiso ficticio")).toBeInTheDocument();
    expect(screen.queryByText("Admin ficticio")).not.toBeInTheDocument();
  });

  it("TRIANGULATE: matriz rol×ruta del spec", () => {
    expect(ROLE_ROUTES.agenda).toEqual(["propietario", "odontologo", "recepcion", "asistente"]);
    expect(ROLE_ROUTES.pacientes).toEqual(["propietario", "odontologo", "recepcion", "asistente"]);
    expect(ROLE_ROUTES.caja).toEqual(["propietario", "recepcion", "odontologo"]);
    expect(ROLE_ROUTES.reportes).toEqual(["propietario", "recepcion", "odontologo"]);
    expect(ROLE_ROUTES.admin).toEqual(["propietario"]);

    presetSession({ roles: ["propietario"] });
    const { unmount } = render(
      <MemoryRouter initialEntries={["/admin"]}>
        <Routes>
          <Route path="/403" element={<p>Sin permiso ficticio</p>} />
          <Route
            path="/admin"
            element={
              <RequireAuth>
                <RequireRole allowed={ROLE_ROUTES.admin}>
                  <p>Admin ficticio</p>
                </RequireRole>
              </RequireAuth>
            }
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("Admin ficticio")).toBeInTheDocument();
    unmount();
    cleanup();

    presetSession({ roles: ["odontologo"] });
    renderAt("/caja");
    expect(screen.getByText("Caja ficticia")).toBeInTheDocument();
  });

  it("TRIANGULATE: el guard reevalúa ante cambio de roles sin recarga", async () => {
    // Ruta privada ABIERTA (autorizada) que pierde el permiso en caliente.
    presetSession({ roles: ["propietario"] });
    renderAt("/admin");
    expect(screen.getByText("Admin ficticio")).toBeInTheDocument();

    useAuthStore.setState((s) => ({
      user: s.user === null ? s.user : { ...s.user, roles: ["recepcion"] as Role[] },
    }));

    expect(await screen.findByText("Sin permiso ficticio")).toBeInTheDocument();
    expect(screen.queryByText("Admin ficticio")).not.toBeInTheDocument();
  });
});
