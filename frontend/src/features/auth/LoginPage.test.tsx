/** RED — task 2.4: LoginPage render (ok redirige a `from`; 401 muestra error y permanece).
 * Datos 100% ficticios.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

async function renderLogin(initialFrom: string | null) {
  const { LoginPage } = await import("./LoginPage");
  const state = initialFrom === null ? undefined : { from: initialFrom };
  return render(
    <MemoryRouter initialEntries={[{ pathname: "/login", state }]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/caja" element={<p>Caja ficticia</p>} />
        <Route path="/agenda" element={<p>Agenda ficticia</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("LoginPage (RED 2.4)", () => {
  beforeEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
    vi.resetModules();
  });

  it("login válido redirige a la ruta `from` recordada", async () => {
    const fetchImpl = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/api/auth/login")) {
        return jsonResponse(200, { accessToken: "access-ficticio-6" });
      }
      if (url.endsWith("/api/auth/me")) {
        return jsonResponse(200, {
          id: "u-ficticia-6",
          email: "recepcion@ficticio.test",
          roles: ["recepcion"],
          tenantId: "t-ficticio-1",
        });
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchImpl);

    await renderLogin("/caja");
    const userEv = userEvent.setup();
    await userEv.type(screen.getByLabelText(/email/i), "recepcion@ficticio.test");
    await userEv.type(screen.getByLabelText(/contrase/i), "Secreta123");
    await userEv.click(screen.getByRole("button", { name: /ingresar/i }));

    await waitFor(() => {
      expect(screen.getByText("Caja ficticia")).toBeInTheDocument();
    });
  });

  it("401 muestra error genérico y permanece en /login", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(401, { detail: "bad" }));
    vi.stubGlobal("fetch", fetchImpl);

    await renderLogin(null);
    const userEv = userEvent.setup();
    await userEv.type(screen.getByLabelText(/email/i), "nadie@ficticio.test");
    await userEv.type(screen.getByLabelText(/contrase/i), "Wrong123");
    await userEv.click(screen.getByRole("button", { name: /ingresar/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Credenciales inválidas. Verificá e intentá de nuevo.",
      );
    });
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
  });

  it("TRIANGULATE: sin `from` redirige a la ruta por defecto del rol (/agenda)", async () => {
    const fetchImpl = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/api/auth/login")) {
        return jsonResponse(200, { accessToken: "access-ficticio-7" });
      }
      if (url.endsWith("/api/auth/me")) {
        return jsonResponse(200, {
          id: "u-ficticia-7",
          email: "asistente@ficticio.test",
          roles: ["asistente"],
          tenantId: "t-ficticio-1",
        });
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchImpl);

    await renderLogin(null);
    const userEv = userEvent.setup();
    await userEv.type(screen.getByLabelText(/email/i), "asistente@ficticio.test");
    await userEv.type(screen.getByLabelText(/contrase/i), "Secreta123");
    await userEv.click(screen.getByRole("button", { name: /ingresar/i }));

    await waitFor(() => {
      expect(screen.getByText("Agenda ficticia")).toBeInTheDocument();
    });
  });
});
