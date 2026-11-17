import { useParams } from "react-router-dom";
import "./public-pages.css";

export function ReservarPage(): JSX.Element {
  const { slug } = useParams<{ slug: string }>();

  return (
    <main className="public-page">
      <p className="public-eyebrow">Reserva online</p>
      <h1>Reservar turno</h1>
      <p className="public-subtitle">Consultorio · {slug}</p>
      <section className="public-card-grid">
        <article className="public-card">
          <span className="public-step">01</span>
          <h2>Prestación</h2>
          <p>Seleccione una prestación disponible.</p>
        </article>
        <article className="public-card">
          <span className="public-step">02</span>
          <h2>Profesional y horario</h2>
          <p>Seleccione profesional y horario.</p>
        </article>
      </section>
    </main>
  );
}
