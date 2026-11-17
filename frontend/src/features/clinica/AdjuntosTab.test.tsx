/** C-15 task 4.6: multipart upload, list and signed-URL opening. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AdjuntosTab } from "./AdjuntosTab";
import {
  callsFor,
  jsonResponse,
  seedSession,
  stubFetch,
} from "./clinica-test-utils";

const ADJUNTO = {
  id: "a-1",
  historia_clinica_id: "h-1",
  tipo: "rx",
  storage_key: "t-ficticio-1/h-1/clave-interna-ficticia",
  nombre_original: "rx-ficticia.pdf",
  content_type: "application/pdf",
  size_bytes: 2048,
  sha256: "sha-ficticio",
  origen: "consulta",
  created_at: "2030-01-10T10:00:00Z",
};

describe("AdjuntosTab (C-15 4.6)", () => {
  beforeEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
    seedSession();
  });

  it("sube un PDF ficticio como multipart con tipo y origen", async () => {
    const fetchImpl = stubFetch((url, init) => {
      const method = init?.method ?? "GET";
      if (url.includes("/adjuntos") && method === "GET") {
        return jsonResponse(200, []);
      }
      if (url.includes("/adjuntos") && method === "POST") {
        return jsonResponse(201, ADJUNTO);
      }
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });

    render(<AdjuntosTab historiaId="h-1" canWrite />);
    const userEv = userEvent.setup();
    await screen.findByText("Todavía no hay adjuntos en la historia.");

    const archivo = new File(["rx-ficticia"], "rx-ficticia.pdf", {
      type: "application/pdf",
    });
    await userEv.upload(
      screen.getByLabelText("Archivo (imagen o PDF)"),
      archivo,
    );
    await userEv.type(screen.getByLabelText("Origen"), "consulta");
    await userEv.click(screen.getByRole("button", { name: "Subir adjunto" }));

    expect(await screen.findByText("rx-ficticia.pdf")).toBeInTheDocument();
    expect(screen.getByText("Tipo: rx")).toBeInTheDocument();
    const [, init] = callsFor(fetchImpl, "POST")[0];
    const form = init?.body as FormData;
    expect(form.get("tipo")).toBe("rx");
    expect(form.get("origen")).toBe("consulta");
    expect(form.get("turno_id")).toBeNull();
    expect(new Headers(init?.headers).get("content-type")).toBeNull();
  });

  it("muestra el 422 de archivo rechazado sin agregarlo a la lista", async () => {
    stubFetch((url, init) => {
      const method = init?.method ?? "GET";
      if (url.includes("/adjuntos") && method === "GET") {
        return jsonResponse(200, []);
      }
      if (url.includes("/adjuntos") && method === "POST") {
        return jsonResponse(422, { detail: "tipo de archivo no permitido" });
      }
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });

    render(<AdjuntosTab historiaId="h-1" canWrite />);
    const userEv = userEvent.setup({ applyAccept: false });
    await screen.findByText("Todavía no hay adjuntos en la historia.");

    await userEv.upload(
      screen.getByLabelText("Archivo (imagen o PDF)"),
      new File(["contenido"], "ejecutable.exe", {
        type: "application/x-msdownload",
      }),
    );
    await userEv.click(screen.getByRole("button", { name: "Subir adjunto" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "tipo de archivo no permitido",
    );
    expect(screen.getByText("Todavía no hay adjuntos en la historia.")).toBeInTheDocument();
  });

  it("abre el adjunto con la URL firmada sin exponer la clave de storage", async () => {
    const openMock = vi.fn();
    vi.stubGlobal("open", openMock);
    stubFetch((url, init) => {
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/historias-clinicas/h-1/adjuntos") && method === "GET") {
        return jsonResponse(200, [ADJUNTO]);
      }
      if (url.endsWith("/api/adjuntos/a-1/url") && method === "GET") {
        return jsonResponse(200, {
          url: "https://storage.ficticio.test/firmada?token=ficticio",
          expires_at: "2030-01-10T11:00:00Z",
        });
      }
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });

    render(<AdjuntosTab historiaId="h-1" canWrite />);
    const userEv = userEvent.setup();
    await screen.findByText("rx-ficticia.pdf");

    expect(
      screen.queryByText(/clave-interna-ficticia/),
    ).not.toBeInTheDocument();
    await userEv.click(screen.getByRole("button", { name: "Abrir adjunto" }));

    await waitFor(() => {
      expect(openMock).toHaveBeenCalledWith(
        "https://storage.ficticio.test/firmada?token=ficticio",
        "_blank",
        "noopener,noreferrer",
      );
    });
  });
});
