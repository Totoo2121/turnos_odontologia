import "./public-pages.css";

export function PortalTurnoPage(): JSX.Element {
  return (
    <main className="public-page">
      <p className="public-eyebrow">Portal del paciente</p>
      <h1>Mi turno</h1>
      <p className="public-subtitle">Consultá las opciones disponibles para tu turno.</p>
      <section className="public-card public-portal-actions">
        <button type="button">Cancelar turno</button>
        <button type="button">Reprogramar turno</button>
      </section>
    </main>
  );
}
