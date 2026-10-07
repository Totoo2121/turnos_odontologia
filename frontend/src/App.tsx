import { useEffect } from "react";
import { AppRouter } from "./app/router";
import { useAuthStore } from "./features/auth/auth-store";

/** Raíz: hidrata la sesión (cookie HttpOnly) y monta el router del shell. */
export function App(): JSX.Element {
  const hydrate = useAuthStore((s) => s.hydrate);

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

  return <AppRouter />;
}
