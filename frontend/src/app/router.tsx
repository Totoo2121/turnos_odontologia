import { Suspense, lazy } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./AppShell";
import { AuthLayout } from "./AuthLayout";
import { ROLE_ROUTES, RequireAuth, RequireRole } from "./guards";
import { LoginPage } from "../features/auth/LoginPage";
import { Forbidden } from "../pages/Forbidden";
import { NotFound } from "../pages/NotFound";

/**
 * Router del shell (D1: react-router-dom v6 + lazy por ruta + Suspense).
 *
 * NOTA DE DEPLOY (rewrite SPA): BrowserRouter exige que el servidor
 * estático redirija todo a index.html (`/* → /index.html`, HTTP 200).
 * Sin ese rewrite, recargar /agenda (o deep-link) devuelve 404 del
 * servidor. El `dev`/`preview` de Vite ya lo resuelven; configurarlo
 * en el hosting (ej. vercel.json rewrites, nginx try_files, S3+CF
 * custom error response) antes de exponer estas rutas.
 */

const AgendaPage = lazy(() => import("../features/agenda/AgendaPage").then((m) => ({ default: m.AgendaPage })));
const ReservarPage = lazy(() => import("../pages/ReservarPage").then((m) => ({ default: m.ReservarPage })));
const PortalTurnoPage = lazy(() => import("../pages/PortalTurnoPage").then((m) => ({ default: m.PortalTurnoPage })));
const PacientesPage = lazy(() =>
  import("../features/clinica/PacientesPage").then((m) => ({
    default: m.PacientesPage,
  })),
);
const PacienteDetallePage = lazy(() =>
  import("../features/clinica/PacienteFichaPage").then((m) => ({
    default: m.PacienteFichaPage,
  })),
);
const CajaPage = lazy(() =>
  import("../features/caja/CajaPage").then((m) => ({ default: m.CajaPage })),
);
const ReportesPage = lazy(() => import("../features/reportes/ReportesPage").then((m) => ({ default: m.ReportesPage })));
const AdminPage = lazy(() => import("../pages/AdminPage"));

function RouteFallback(): JSX.Element {
  return <p>Cargando…</p>;
}

/** Rutas testeables sin BrowserRouter (los tests montan MemoryRouter). */
export function AppRoutes(): JSX.Element {
  return (
    <Routes>
      <Route element={<AuthLayout />}>
        <Route path="/login" element={<LoginPage />} />
      </Route>
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route
          path="/agenda"
          element={
            <RequireRole allowed={ROLE_ROUTES.agenda}>
              <Suspense fallback={<RouteFallback />}>
                <AgendaPage />
              </Suspense>
            </RequireRole>
          }
        />
        <Route
          path="/pacientes"
          element={
            <RequireRole allowed={ROLE_ROUTES.pacientes}>
              <Suspense fallback={<RouteFallback />}>
                <PacientesPage />
              </Suspense>
            </RequireRole>
          }
        />
        <Route
          path="/pacientes/:id"
          element={
            <RequireRole allowed={ROLE_ROUTES.pacientes}>
              <Suspense fallback={<RouteFallback />}>
                <PacienteDetallePage />
              </Suspense>
            </RequireRole>
          }
        />
        <Route
          path="/caja"
          element={
            <RequireRole allowed={ROLE_ROUTES.caja}>
              <Suspense fallback={<RouteFallback />}>
                <CajaPage />
              </Suspense>
            </RequireRole>
          }
        />
        <Route
          path="/reportes"
          element={
            <RequireRole allowed={ROLE_ROUTES.reportes}>
              <Suspense fallback={<RouteFallback />}>
                <ReportesPage />
              </Suspense>
            </RequireRole>
          }
        />
        <Route
          path="/admin"
          element={
            <RequireRole allowed={ROLE_ROUTES.admin}>
              <Suspense fallback={<RouteFallback />}>
                <AdminPage />
              </Suspense>
            </RequireRole>
          }
        />
        <Route path="/403" element={<Forbidden />} />
        <Route path="*" element={<NotFound />} />
      </Route>
      <Route
        path="/reservar/:slug"
        element={
          <Suspense fallback={<RouteFallback />}>
            <ReservarPage />
          </Suspense>
        }
      />
      <Route
        path="/p/:token"
        element={
          <Suspense fallback={<RouteFallback />}>
            <PortalTurnoPage />
          </Suspense>
        }
      />
      <Route path="/" element={<Navigate to="/agenda" replace />} />
    </Routes>
  );
}

/** Router de producción (BrowserRouter + rutas). */
export function AppRouter(): JSX.Element {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
