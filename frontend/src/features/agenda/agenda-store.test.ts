import { describe, it, expect } from "vitest";
import { useAgendaStore } from "./agenda-store";

describe("agenda store", () => {
  it("cambia vista", () => {
    useAgendaStore.getState().setVista("semana");
    expect(useAgendaStore.getState().vista).toBe("semana");
    useAgendaStore.getState().setVista("dia");
  });
});