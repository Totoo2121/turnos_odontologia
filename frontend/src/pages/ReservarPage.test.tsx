/** Task 3.2: E2E reserva sin cuenta (smoke). Datos ficticios. */
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { ReservarPage } from "./ReservarPage";

describe("ReservarPage (reserva sin cuenta)", () => {
  beforeEach(() => cleanup());

  it("renderiza la página pública de reserva para un slug ficticio", () => {
    render(
      <MemoryRouter initialEntries={["/reservar/clinica-ficticia"]}>
        <Routes>
          <Route path="/reservar/:slug" element={<ReservarPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: /reservar turno/i })).toBeInTheDocument();
    expect(screen.getByText(/clinica-ficticia/)).toBeInTheDocument();
  });
});