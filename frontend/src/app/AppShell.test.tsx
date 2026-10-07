/** RED — task 3.2: AppShell (nav por rol, logout) + Forbidden/NotFound. Datos ficticios. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "./AppShell";
import { Forbidden } from "../pages/Forbidden";
import { NotFound } from "../pages/NotFound";
import { useAuthStore, type Role } from "../features/auth/auth-store";

function presetSession(roles: Role[]): void {
  useAuthStore.setState({
    accessToken: "access-ficticio-s",
    user: {
      id: "u-ficticia-s",
      email: "recepcion@ficticio.test",
      roles,
      tenantId: "t-ficticio-1",
    },
    status: "authenticated",
    error: null,
  });
}

function renderShell(initialPath: string): void {
  render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/login" element={<p>Página de ingreso ficticia</p>} />
        <Route element={<AppShell />}>
          <Route path="/agenda" element={<p>Agenda ficticia</p>} />
          <Route path="/403" element={<Forbidden />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("AppShell (RED 3.2)", () => {
  beforeEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("recepción ve agenda/pacientes/caja/reportes y NO ve admin en el nav", () => {
    presetSession(["recepcion"]);
    renderShell("/agenda");

    const nav = screen.getByRole("navigation", { name: /principal/i });
    expect(nav).toHaveTextContent("Agenda");
    expect(nav).toHaveTextContent("Pacientes");
    expect(nav).toHaveTextContent("Caja");
    expect(nav).toHaveTextContent("Reportes");
    expect(nav).not.toHaveTextContent("Admin");
  });

  it("logout desde el header termina en /login", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({}), { status: 200 }));
    vi.stubGlobal("fetch", fetchImpl);
    presetSession(["recepcion"]);
    renderShell("/agenda");

    const userEv = userEvent.setup();
    await userEv.click(screen.getByRole("button", { name: /cerrar sesi/i }));

    await waitFor(() => {
      expect(screen.getByText("Página de ingreso ficticia")).toBeInTheDocument();
    });
  });

  it("TRIANGULATE: ruta desconocida con sesión muestra NotFound dentro del shell", () => {
    presetSession(["recepcion"]);
    renderShell("/ruta-que-no-existe");

    expect(screen.getByText(/no encontrada/i)).toBeInTheDocument();
    // Header/nav del shell intactos.
    expect(screen.getByText("recepcion@ficticio.test")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: /principal/i })).toBeInTheDocument();
  });

  it("TRIANGULATE: Forbidden ofrece volver a la agenda", () => {
    presetSession(["asistente"]);
    render(
      <MemoryRouter initialEntries={["/403"]}>
        <Routes>
          <Route path="/403" element={<Forbidden />} />
          <Route path="/agenda" element={<p>Agenda ficticia</p>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText(/sin permiso/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /agenda/i })).toHaveAttribute("href", "/agenda");
  });
});
