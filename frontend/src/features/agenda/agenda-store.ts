import { create } from "zustand";
import { todayIso } from "../../shared/format";

export type Vista = "dia" | "semana";

export interface Turno {
  id: string;
  profesionalId: string;
  sillónId: string;
  inicio: string;
  fin: string;
  estado: string;
  cobro: string;
  sobreturno: boolean;
}

export interface AgendaState {
  vista: Vista;
  fecha: string;
  profesionalId: string | null;
  sillonId: string | null;
  turnos: Turno[];
  setVista: (v: Vista) => void;
  setFecha: (f: string) => void;
  setProfesional: (id: string | null) => void;
  setSillon: (id: string | null) => void;
  setTurnos: (t: Turno[]) => void;
  addTurno: (t: Turno) => void;
  updateTurno: (id: string, patch: Partial<Turno>) => void;
}

export const useAgendaStore = create<AgendaState>((set) => ({
  vista: "dia",
  fecha: todayIso(),
  profesionalId: null,
  sillonId: null,
  turnos: [],
  setVista: (vista) => set({ vista }),
  setFecha: (fecha) => set({ fecha }),
  setProfesional: (profesionalId) => set({ profesionalId }),
  setSillon: (sillonId) => set({ sillonId }),
  setTurnos: (turnos) => set({ turnos }),
  addTurno: (t) => set((s) => ({ turnos: [...s.turnos, t] })),
  updateTurno: (id, patch) =>
    set((s) => ({
      turnos: s.turnos.map((t) => (t.id === id ? { ...t, ...patch } : t)),
    })),
}));
