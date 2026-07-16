import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";
import { AdminLogin } from "./admin/AdminLogin";
import { AdminShell } from "./admin/AdminShell";
import { CompaniesPage } from "./admin/CompaniesPage";
import { PlatformDashboard } from "./admin/PlatformDashboard";
import { ClientLogin } from "./client/ClientLogin";
import { ClientShell } from "./client/ClientShell";
import { ComingSoon } from "./client/ComingSoon";
import { DashboardPage } from "./client/dashboard/DashboardPage";
import { getTokens } from "./shared/api";

function RequireClient(props: { children: React.ReactNode }) {
  return getTokens("client") ? <>{props.children}</> : <Navigate to="/login" replace />;
}

function RequireAdmin(props: { children: React.ReactNode }) {
  return getTokens("admin") ? <>{props.children}</> : <Navigate to="/admin/login" replace />;
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<ClientLogin />} />
        <Route
          path="/app"
          element={
            <RequireClient>
              <ClientShell />
            </RequireClient>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path=":module/*" element={<ComingSoon />} />
        </Route>

        <Route path="/admin/login" element={<AdminLogin />} />
        <Route
          path="/admin"
          element={
            <RequireAdmin>
              <AdminShell />
            </RequireAdmin>
          }
        >
          <Route index element={<PlatformDashboard />} />
          <Route path="companies" element={<CompaniesPage />} />
        </Route>

        <Route path="*" element={<Navigate to="/app" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
