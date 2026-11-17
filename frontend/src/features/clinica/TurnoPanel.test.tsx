/** C-15 task 4.9: close the appointment + schedule the recall date. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { addDaysIso, todayIso } from "../../shared/format";
import { TurnoPanel } from "./TurnoPanel";
import {
  callsFor,
  jsonResponse,
  seedSession,
  stubFetch,
} from "./clinica-test-utils";

const TURNO = {
  id: "t-1",
  inicio: "2030-01-10T12:00:00Z",
  fin: "2030-01-10T12:40:00Z",
  estado: "pendiente",
  profesional_id: "prof-1",
  sillon_id: "sil-1",
  prestacion_id: "prest-1",
  paciente_id: "p-1",
  sobreturno: false,
  cobro: "sin-sena",
  cobro_monto: null,
};

const PRESTACION = {
  id: "prest-1",
  nombre: "Control ficticio",
  duracion_min: 30,
  buffer_min: 10,
  precio: "10000.00",
  requiere_consentimiento: false,
  intervalo_control_dias: 180,
  is_active: true,
};

const PROFESIONAL = {
  id: "prof-1",
  nombre: "Odontólogo Ficticio",
  matricula: "MP-000",
  especialidades: [],
  prestacion_ids: ["prest-1"],
  activo: true,
};

const SILLON = { id: "sil-1", nombre: "Sillón Ficticio 1", activo: true };

function expectedControlDate(): string {
  const iso = addDaysIso(todayIso(), 180);
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

function baseHandler(
  extra: (url: string, init?: RequestInit) => Response | null = () => null,
) {
  return stubFetch((url, init) => {
    const method = init?.method ?? "GET";
    const custom = extra(url, init);
    if (custom !== null) {
      return custom;
    }
    if (url.includes("/api/turnos/agenda") && method === "GET") {
      return jsonResponse(200, [TURNO]);
    }
    if (url.endsWith("/api/prestaciones") && method === "GET") {
      return jsonResponse(200, [PRESTACION]);
    }
    if (url.endsWith("/api/profesionales") && method === "GET") {
      return jsonResponse(200, [PROFESIONAL]);
    }
    if (url.endsWith("/api/sillones") && method === "GET") {
      return jsonResponse(200, [SILLON]);
    }
    throw new Error(`unexpected fetch: ${method} ${url}`);
  });
}

describe("TurnoPanel (C-15 4.9)", () => {
  beforeEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
    seedSession();
  });

  it("cierra el turno abierto como atendido", async () => {
    baseHandler((url, init) => {
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/turnos/t-1/estado") && method === "PATCH") {
        return jsonResponse(200, { ...TURNO, estado: "atendido" });
      }
      return null;
    });
    const userEv = userEvent.setup();

    render(<TurnoPanel pacienteId="p-1" canClose canSchedule />);
    await screen.findByRole("button", { name: "Marcar atendido" });
    await userEv.click(
      screen.getByRole("button", { name: "Marcar atendido" }),
    );

    expect(await screen.findByText("Turno cerrado como atendido.")).toBeInTheDocument();
    expect(screen.getByText("Atendido")).toBeInTheDocument();
  });

  it("muestra la fecha de control sugerida por el intervalo", async () => {
    baseHandler();

    render(<TurnoPanel pacienteId="p-1" canClose canSchedule={false} />);

    expect(
      await screen.findByText(
        `Control sugerido: ${expectedControlDate()} (cada 180 días).`,
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Agendar control" }),
    ).not.toBeInTheDocument();
  });

  it("recepción agenda el control con prestación y fecha elegidas", async () => {
    const fetchImpl = baseHandler((url, init) => {
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/turnos") && method === "POST") {
        const body = JSON.parse(String(init?.body)) as {
          inicio: string;
          profesional_id: string;
          sillon_id: string;
          prestacion_id: string;
          paciente_id: string;
        };
        return jsonResponse(201, {
          id: "t-control",
          paciente_id: body.paciente_id,
          profesional_id: body.profesional_id,
          sillon_id: body.sillon_id,
          prestacion_id: body.prestacion_id,
          inicio: body.inicio,
          fin: "2030-06-01T09:40:00Z",
          estado: "pendiente",
          origen: "control",
          sobreturno: false,
        });
      }
      return null;
    });
    const userEv = userEvent.setup();

    render(<TurnoPanel pacienteId="p-1" canClose canSchedule />);
    const boton = await screen.findByRole("button", {
      name: "Agendar control",
    });
    expect(screen.getByLabelText("Fecha")).toHaveValue(
      addDaysIso(todayIso(), 180),
    );
    await userEv.click(boton);

    expect(await screen.findByText("Turno de control agendado.")).toBeInTheDocument();
    const [, init] = callsFor(fetchImpl, "POST")[0];
    expect(JSON.parse(String(init?.body))).toMatchObject({
      paciente_id: "p-1",
      profesional_id: "prof-1",
      sillon_id: "sil-1",
      prestacion_id: "prest-1",
      origen: "control",
    });
    expect(
      (JSON.parse(String(init?.body)) as { inicio: string }).inicio,
    ).toBe(`${addDaysIso(todayIso(), 180)}T09:00:00`);
  });

  it("muestra el conflicto 409 al agendar un control solapado", async () => {
    baseHandler((url, init) => {
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/turnos") && method === "POST") {
        return jsonResponse(409, { detail: "el horario se solapa con otro turno" });
      }
      return null;
    });
    const userEv = userEvent.setup();

    render(<TurnoPanel pacienteId="p-1" canClose canSchedule />);
    const boton = await screen.findByRole("button", {
      name: "Agendar control",
    });
    await userEv.click(boton);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "el horario se solapa con otro turno",
      );
    });
  });
});
