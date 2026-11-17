import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { useAuthStore } from "../auth/auth-store";
import { getAusentismo, getOcupacion, getRecaudacion } from "./reportes-api";
import { ReportesPage } from "./ReportesPage";

vi.mock("./reportes-api", () => ({
  getAusentismo: vi.fn(),
  getOcupacion: vi.fn(),
  getRecaudacion: vi.fn(),
}));

describe("ReportesPage", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    useAuthStore.setState({
      user: { id: "u-ficticio", email: "dueno@example.invalid", roles: ["propietario"], tenantId: "t-ficticio" },
      status: "authenticated",
    });
    vi.mocked(getOcupacion).mockResolvedValue({
      desde: "2026-11-01", hasta: "2026-11-16", alcance: "total",
      filas: [{ profesional_id: "prof-1", profesional: "Profesional Ficticio", turnos: 3, minutos_ocupados: 90, atendidos: 2, ausentes: 1, cancelados: 0 }],
    });
    vi.mocked(getAusentismo).mockResolvedValue({
      desde: "2026-11-01", hasta: "2026-11-16", alcance: "total",
      filas: [{ profesional_id: "prof-1", profesional: "Profesional Ficticio", turnos: 3, ausentes: 1, cancelados: 0, tasa_ausentismo: 33.33 }],
    });
    vi.mocked(getRecaudacion).mockResolvedValue({
      desde: "2026-11-01", hasta: "2026-11-16", alcance: "total",
      senias_acreditadas: "15000.00", cobros_cuenta_corriente: "25000.00",
      total_cobrado: "40000.00", cantidad_cobros_cuenta_corriente: 1,
      deuda_neta_planes: "10000.00", por_profesional: [],
    });
  });

  it("muestra ocupación, ausentismo y recaudación para propietario", async () => {
    render(<ReportesPage />);
    expect(await screen.findByRole("heading", { name: "Ocupación por profesional" })).toBeInTheDocument();
    expect(screen.getAllByText("Profesional Ficticio")).toHaveLength(2);
    expect(screen.getByText(/40\.000,00/)).toBeInTheDocument();
    expect(screen.getByText(/no un porcentaje contra capacidad/)).toBeInTheDocument();
  });

  it("no carga recaudación para recepción", async () => {
    useAuthStore.setState({
      user: { id: "u-ficticio", email: "recepcion@example.invalid", roles: ["recepcion"], tenantId: "t-ficticio" },
    });
    render(<ReportesPage />);
    expect(await screen.findByRole("heading", { name: "Ausentismo" })).toBeInTheDocument();
    expect(getRecaudacion).not.toHaveBeenCalled();
    expect(screen.queryByRole("heading", { name: "Recaudación" })).not.toBeInTheDocument();
  });
});
