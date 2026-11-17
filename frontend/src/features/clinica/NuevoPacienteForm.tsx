import { useRef, useState, type FormEvent } from "react";
import { ApiError } from "../../shared/api-client";
import { createPaciente, mensajeError, type Paciente } from "./clinica-api";

export function NuevoPacienteForm({ onCreated, onCancel }: {
  onCreated: (paciente: Paciente) => void;
  onCancel: () => void;
}): JSX.Element {
  const submitting = useRef(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (submitting.current) return;
    const data = new FormData(event.currentTarget);
    const value = (key: string) => String(data.get(key) ?? "").trim();
    const nombre = value("nombre");
    const telefono = value("telefono");
    if (!nombre || !telefono) {
      setError("Completá el nombre y el teléfono.");
      return;
    }
    submitting.current = true;
    setSaving(true);
    setError(null);
    const consentimiento = data.get("consentimiento") === "on";
    try {
      const paciente = await createPaciente({
        nombre, telefono,
        dni: value("dni") || null,
        email: value("email") || null,
        obra_social: value("obra_social") || null,
        consentimiento_datos: consentimiento,
        consentimiento_at: consentimiento ? new Date().toISOString() : null,
      });
      onCreated(paciente);
    } catch (cause: unknown) {
      setError(cause instanceof ApiError && cause.status === 409
        ? "Ya existe un paciente con ese DNI en la clínica."
        : mensajeError(cause));
    } finally {
      submitting.current = false;
      setSaving(false);
    }
  }

  return (
    <section className="ficha-card" aria-labelledby="nuevo-paciente-title">
      <h2 id="nuevo-paciente-title">Nuevo paciente</h2>
      <p className="clinica-muted">Nombre y teléfono son obligatorios. Los demás datos son opcionales.</p>
      <form onSubmit={(event) => void submit(event)} aria-busy={saving}>
        <fieldset className="paciente-form-fields" disabled={saving}>
          <div className="ficha-grid-2">
            <label>Nombre y apellido<input name="nombre" maxLength={160} autoComplete="name" required autoFocus /></label>
            <label>Teléfono<input name="telefono" type="tel" maxLength={32} autoComplete="tel" required /></label>
            <label>DNI<input name="dni" maxLength={20} /></label>
            <label>Email<input name="email" type="email" maxLength={320} autoComplete="email" /></label>
            <label>Obra social<input name="obra_social" maxLength={120} /></label>
          </div>
          <label className="paciente-consentimiento"><input name="consentimiento" type="checkbox" />El paciente otorgó su consentimiento para el tratamiento de sus datos personales.</label>
          {error ? <p role="alert" className="clinica-error">{error}</p> : null}
          <div className="ficha-actions">
            <button type="submit">{saving ? "Guardando…" : "Guardar paciente"}</button>
            <button type="button" onClick={onCancel}>Cancelar</button>
          </div>
        </fieldset>
      </form>
    </section>
  );
}
