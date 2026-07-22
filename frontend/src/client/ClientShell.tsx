// Tenant shell: sidebar filtered by role map + enabled modules — a module at
// NONE never appears in navigation (docs/AUTH_RBAC.md acceptance). Chrome is the
// design-system AppShell; screen content flows through RouteTransition.

import {
  Contact,
  FolderKanban,
  LayoutDashboard,
  LogOut,
  Package,
  Receipt,
  Settings,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { clientLogout, clientMe } from "../shared/auth";
import { AppShell, type CommandItem, RouteTransition, type ShellNavItem } from "../shared/shell";
import type { ClientMe } from "../shared/types";
import { Spinner } from "../shared/ui/Spinner/Spinner";

const DASHBOARD: ShellNavItem = {
  key: "dashboard",
  label: "Dashboard",
  to: "/app",
  end: true,
  icon: <LayoutDashboard size={20} />,
};

const MODULES: { key: string; label: string; route: string; icon: ReactNode }[] = [
  { key: "projects", label: "Projects", route: "/app/projects", icon: <FolderKanban size={20} /> },
  { key: "crm", label: "CRM", route: "/app/crm", icon: <Contact size={20} /> },
  { key: "inventory", label: "Inventory", route: "/app/inventory", icon: <Package size={20} /> },
  { key: "finance", label: "Finance", route: "/app/finance", icon: <Receipt size={20} /> },
  { key: "settings", label: "Settings", route: "/app/settings", icon: <Settings size={20} /> },
];

export function ClientShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const [me, setMe] = useState<ClientMe | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    clientMe().then(setMe).catch(() => setError(true));
  }, []);

  useEffect(() => {
    if (error) navigate("/login");
  }, [error, navigate]);

  if (!me) {
    return (
      <div style={{ minHeight: "100dvh", display: "grid", placeItems: "center" }}>
        <Spinner size="lg" />
      </div>
    );
  }

  async function logout() {
    await clientLogout();
    navigate("/login");
  }

  const visibleModules = MODULES.filter(
    (m) =>
      me.company.enabled_modules.includes(m.key) &&
      (me.role.permissions[m.key] ?? 0) >= 1, // ≥ VIEW
  );

  const nav: ShellNavItem[] = [
    DASHBOARD,
    ...visibleModules.map((m) => ({ key: m.key, label: m.label, to: m.route, icon: m.icon })),
  ];

  const current = visibleModules.find((m) => location.pathname.startsWith(m.route));
  const title = current ? current.label : "Dashboard";

  const commands: CommandItem[] = [
    ...nav.map((item) => ({
      id: `nav-${item.key}`,
      label: item.label,
      group: "Navigate",
      icon: item.icon,
      onSelect: () => navigate(item.to),
    })),
    {
      id: "sign-out",
      label: "Sign out",
      group: "Account",
      icon: <LogOut size={18} />,
      onSelect: () => void logout(),
    },
  ];

  return (
    <AppShell
      brand={{ title: me.company.name, subtitle: "Blyns workspace" }}
      nav={nav}
      user={{ name: me.name, role: me.role.name }}
      onSignOut={() => void logout()}
      title={title}
      breadcrumbs={[{ label: title }]}
      commands={commands}
      mobileTabs={nav.slice(0, 5)}
    >
      <RouteTransition context={me} />
    </AppShell>
  );
}
