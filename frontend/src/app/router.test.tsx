/** RED — task 3.3: router + placeholders (render por rol). Datos ficticios. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AppRoutes } from "./router";
import { useAuthStore, type Role } from "../features/auth/auth-store";

function presetSession(roles: Role[] | null): void {
  if (roles === null) {
    useAuthStore.setState({
      accessToken: null,
      user: null,
      status: "unauthenticated",
      error: null,
    });
  } else {
    useAuthStore.setState({
      accessToken: "access-ficticio-r",
      user: {
        id: "u-ficticia-r",
        email: "recepcion@ficticio.test",
        roles,
        tenantId: "t-ficticio-1",
      },
      status: "authenticated",
      error: null,
    });
  }
}

function renderPath(path: string): void {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe("router + placeholders (RED 3.3)", () => {
  beforeEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("recepción en /agenda ve el placeholder de agenda dentro del shell", async () => {
    presetSession(["recepcion"]);
    renderPath("/agenda");

    expect(await screen.findByText("Agenda (ficticio, contenido en C-07)")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: /principal/i })).toBeInTheDocument();
  });

  it("anónimo en /agenda ve el login", () => {
    presetSession(null);
    renderPath("/agenda");

    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: /principal/i })).not.toBeInTheDocument();
  });

  it("TRIANGULATE: /pacientes/abc-123 muestra el identificador de la URL", async () => {
    presetSession(["odontologo"]);
    renderPath("/pacientes/abc-123");

    expect(await screen.findByText(/abc-123/)).toBeInTheDocument();
  });

  it("TRIANGULATE: asistente en /admin ve 403 y /caja le muestra su placeholder", async () => {
    presetSession(["asistente"]);
    renderPath("/admin");
    expect(await screen.findByText(/sin permiso/i)).toBeInTheDocument();
    cleanup();

    presetSession(["recepcion"]);
    renderPath("/caja");
    expect(await screen.findByText("Caja (ficticio, contenido en C-15)")).toBeInTheDocument();
  });
});
