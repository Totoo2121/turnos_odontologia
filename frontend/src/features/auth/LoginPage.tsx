import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { defaultRouteForRoles, useAuthStore } from "./auth-store";
import "./LoginPage.css";

interface LoginLocationState {
  from?: string;
}

/** Formulario de ingreso: email + password, error genérico, redirige a `from` o a la ruta por defecto del rol. */
export function LoginPage(): JSX.Element {
  const login = useAuthStore((s) => s.login);
  const status = useAuthStore((s) => s.status);
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const pending = status === "loading";

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    const result = await login(email, password);
    if (result.ok) {
      const state = location.state as LoginLocationState | null;
      const roles = useAuthStore.getState().user?.roles ?? [];
      navigate(state?.from ?? defaultRouteForRoles(roles), { replace: true });
    } else {
      setError(result.error);
    }
  }

  return (
    <section className="login" aria-labelledby="login-title">
      <h1 id="login-title">Ingresar</h1>
      <form onSubmit={(e) => void handleSubmit(e)}>
        <div className="login-field">
          <label htmlFor="login-email">Email</label>
          <input
            id="login-email"
            name="email"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div className="login-field">
          <label htmlFor="login-password">Contraseña</label>
          <input
            id="login-password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        {error !== null ? <p role="alert" className="login-error">{error}</p> : null}
        <button type="submit" disabled={pending}>
          {pending ? "Ingresando…" : "Ingresar"}
        </button>
      </form>
    </section>
  );
}
