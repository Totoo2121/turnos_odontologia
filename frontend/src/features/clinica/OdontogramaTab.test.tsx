/** C-15 task 4.5: FDI odontogram, estado–superficie validation and 422s. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OdontogramaTab } from "./OdontogramaTab";
import {
  callsFor,
  jsonResponse,
  seedSession,
  stubFetch,
} from "./clinica-test-utils";

function odontogramaVacio(): Record<string, unknown> {
  return {
    id: "od-1",
    historia_clinica_id: "h-1",
    estado_actual: [],
  };
}

function evento(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "ev-1",
    odontograma_id: "od-1",
    pieza_fdi: 16,
    superficie: "oclusal",
    estado: "caries",
    fecha: "2030-01-10T10:00:00Z",
    autor_usuario_id: "u-ficticio-1",
    autor_profesional_id: null,
    observaciones: null,
    created_at: "2030-01-10T10:00:00Z",
    ...overrides,
  };
}

function stubOdontograma(postHandler: (url: string, init?: RequestInit) => Response) {
  return stubFetch((url, init) => {
    const method = init?.method ?? "GET";
    if (url.endsWith("/api/odontogramas/h-1") && method === "GET") {
      return jsonResponse(200, odontogramaVacio());
    }
    if (url.includes("/eventos") && method === "POST") {
      return postHandler(url, init);
    }
    throw new Error(`unexpected fetch: ${method} ${url}`);
  });
}

describe("OdontogramaTab (C-15 4.5)", () => {
  beforeEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
    seedSession();
  });

  it("renderiza las 32 piezas permanentes agrupadas por arcada", async () => {
    stubOdontograma(() => jsonResponse(201, evento()));

    render(<OdontogramaTab historiaId="h-1" canWrite />);

    const piezas = await screen.findAllByRole("button", {
      name: /^Pieza \d+$/,
    });
    expect(piezas).toHaveLength(32);
    expect(screen.getByText("Arcada superior derecha")).toBeInTheDocument();
    expect(screen.getByText("Arcada inferior derecha")).toBeInTheDocument();
    expect(piezas.map((boton) => boton.getAttribute("aria-label"))).toContain(
      "Pieza 48",
    );
  });

  it("registra caries oclusal en la pieza 16 y actualiza la grilla", async () => {
    const fetchImpl = stubOdontograma(() => jsonResponse(201, evento()));
    const userEv = userEvent.setup();

    render(<OdontogramaTab historiaId="h-1" canWrite />);
    await screen.findAllByRole("button", { name: /^Pieza \d+$/ });

    await userEv.click(screen.getByRole("button", { name: "Pieza 16" }));
    await userEv.selectOptions(screen.getByLabelText("Estado"), "caries");
    await userEv.selectOptions(screen.getByLabelText("Superficie"), "oclusal");
    await userEv.click(screen.getByRole("button", { name: "Registrar evento" }));

    await waitFor(() => {
      expect(
        within(screen.getByRole("button", { name: "Pieza 16" })).getByText(
          "caries (oclusal)",
        ),
      ).toBeInTheDocument();
    });
    const [, init] = callsFor(fetchImpl, "POST")[0];
    expect(JSON.parse(String(init?.body))).toMatchObject({
      pieza_fdi: 16,
      estado: "caries",
      superficie: "oclusal",
    });
  });

  it("bloquea corona con superficie sin llamar a la API", async () => {
    const fetchImpl = stubOdontograma(() => jsonResponse(201, evento()));
    const userEv = userEvent.setup();

    render(<OdontogramaTab historiaId="h-1" canWrite />);
    await screen.findAllByRole("button", { name: /^Pieza \d+$/ });

    await userEv.click(screen.getByRole("button", { name: "Pieza 16" }));
    await userEv.selectOptions(screen.getByLabelText("Estado"), "corona");
    await userEv.selectOptions(screen.getByLabelText("Superficie"), "oclusal");
    await userEv.click(screen.getByRole("button", { name: "Registrar evento" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/no admite superficie/i);
    expect(callsFor(fetchImpl, "POST")).toHaveLength(0);
  });

  it("muestra el 422 del backend y no actualiza la pieza", async () => {
    stubOdontograma(() =>
      jsonResponse(422, { detail: "superficie invalida" }),
    );
    const userEv = userEvent.setup();

    render(<OdontogramaTab historiaId="h-1" canWrite />);
    await screen.findAllByRole("button", { name: /^Pieza \d+$/ });

    await userEv.click(screen.getByRole("button", { name: "Pieza 16" }));
    await userEv.selectOptions(screen.getByLabelText("Estado"), "caries");
    await userEv.selectOptions(screen.getByLabelText("Superficie"), "oclusal");
    await userEv.click(screen.getByRole("button", { name: "Registrar evento" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "superficie invalida",
    );
    const pieza16 = screen.getByRole("button", { name: "Pieza 16" });
    expect(within(pieza16).getByText("sin registro")).toBeInTheDocument();
    expect(within(pieza16).queryByText(/caries/)).not.toBeInTheDocument();
  });
});
