/** RED — task 4.1: Table + Modal controlados por props. Datos ficticios. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Table } from "./Table";
import { Modal } from "./Modal";

const COLUMNS = [
  { key: "nombre", header: "Nombre" },
  { key: "hora", header: "Hora" },
];

describe("shared/ui Table+Modal (RED 4.1)", () => {
  beforeEach(() => {
    cleanup();
  });

  it("Table refleja filas y columnas por props", () => {
    render(
      <Table
        columns={COLUMNS}
        rows={[
          { id: "f1", nombre: "Paciente Ficticio Uno", hora: "09:00" },
          { id: "f2", nombre: "Paciente Ficticio Dos", hora: "09:30" },
        ]}
        emptyText="Sin turnos ficticios"
      />,
    );

    expect(screen.getByText("Nombre")).toBeInTheDocument();
    expect(screen.getByText("Paciente Ficticio Uno")).toBeInTheDocument();
    expect(screen.getByText("09:30")).toBeInTheDocument();
    expect(screen.queryByText("Sin turnos ficticios")).not.toBeInTheDocument();
  });

  it("TRIANGULATE: Table sin filas muestra emptyText exacto", () => {
    render(<Table columns={COLUMNS} rows={[]} emptyText="Sin turnos ficticios" />);

    expect(screen.getByText("Sin turnos ficticios")).toBeInTheDocument();
  });

  it("Modal abierto muestra título e hijos; cerrado no renderiza nada", () => {
    const onClose = vi.fn();
    const { unmount } = render(
      <Modal open={true} onClose={onClose} title="Turno ficticio">
        <p>Detalle ficticio</p>
      </Modal>,
    );

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Turno ficticio")).toBeInTheDocument();
    expect(screen.getByText("Detalle ficticio")).toBeInTheDocument();
    unmount();
    cleanup();

    render(
      <Modal open={false} onClose={onClose} title="Turno ficticio">
        <p>Detalle ficticio</p>
      </Modal>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByText("Detalle ficticio")).not.toBeInTheDocument();
  });

  it("TRIANGULATE: Escape cierra el modal (llama onClose una vez)", () => {
    const onClose = vi.fn();
    render(
      <Modal open={true} onClose={onClose} title="Turno ficticio">
        <p>Detalle ficticio</p>
      </Modal>,
    );

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
