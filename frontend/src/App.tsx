import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";
import { AdminLogin } from "./admin/AdminLogin";
import { AdminShell } from "./admin/AdminShell";
import { BookingsPage } from "./admin/BookingsPage";
import { CompaniesPage } from "./admin/CompaniesPage";
import { IpRulesPage } from "./admin/IpRulesPage";
import { PlatformDashboard } from "./admin/PlatformDashboard";
import { ClientLogin } from "./client/ClientLogin";
import { ClientShell } from "./client/ClientShell";
import { ComingSoon } from "./client/ComingSoon";
import { CrmPage } from "./client/crm/CrmPage";
import { DashboardPage } from "./client/dashboard/DashboardPage";
import { FinancePage } from "./client/finance/FinancePage";
import { InventoryPage } from "./client/inventory/InventoryPage";
import { ProductionPage } from "./client/production/ProductionPage";
import { ProjectDetail } from "./client/projects/ProjectDetail";
import { ProjectsPage } from "./client/projects/ProjectsPage";
import { SettingsPage } from "./client/settings/SettingsPage";
import { LandingPage } from "./landing/LandingPage";
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
        {/* Public marketing surface — its own route, no portal shell, no auth. */}
        <Route path="/" element={<LandingPage />} />

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
          <Route path="projects" element={<ProjectsPage />} />
          {/* Static segment, so it outranks projects/:id — otherwise the
              dashboard's "Create a project" shortcut opens a detail page
              for a project literally called "new". */}
          <Route path="projects/new" element={<ProjectsPage />} />
          <Route path="projects/:id" element={<ProjectDetail />} />
          <Route path="production/*" element={<ProductionPage />} />
          <Route path="crm/*" element={<CrmPage />} />
          <Route path="inventory/*" element={<InventoryPage />} />
          <Route path="finance/*" element={<FinancePage />} />
          <Route path="settings/*" element={<SettingsPage />} />
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
          <Route path="discovery-bookings" element={<BookingsPage />} />
          <Route path="ip-rules" element={<IpRulesPage />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
