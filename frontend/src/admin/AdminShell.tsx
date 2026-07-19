import { Building2, LayoutDashboard, LogOut } from "lucide-react";
import { useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { adminLogout, adminMe } from "../shared/auth";
import { AppShell, type CommandItem, type ShellNavItem } from "../shared/shell";
import type { AdminMe } from "../shared/types";
import { Spinner } from "../shared/ui/Spinner/Spinner";

const NAV: ShellNavItem[] = [
  {
    key: "dashboard",
    label: "Platform dashboard",
    to: "/admin",
    end: true,
    icon: <LayoutDashboard size={20} />,
  },
  { key: "companies", label: "Companies", to: "/admin/companies", icon: <Building2 size={20} /> },
];

export function AdminShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const [me, setMe] = useState<AdminMe | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    adminMe().then(setMe).catch(() => setError(true));
  }, []);

  useEffect(() => {
    if (error) navigate("/admin/login");
  }, [error, navigate]);

  if (!me) {
    return (
      <div style={{ minHeight: "100dvh", display: "grid", placeItems: "center" }}>
        <Spinner size="lg" />
      </div>
    );
  }

  async function logout() {
    await adminLogout();
    navigate("/admin/login");
  }

  const current = NAV.find((n) =>
    n.end ? location.pathname === n.to : location.pathname.startsWith(n.to),
  );
  const title = current?.label ?? "Control plane";

  const commands: CommandItem[] = [
    ...NAV.map((item) => ({
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
      brand={{ title: "Admin Portal", subtitle: "Control plane" }}
      nav={NAV}
      user={{ name: me.name, role: me.role.name }}
      onSignOut={() => void logout()}
      title={title}
      breadcrumbs={[{ label: title }]}
      commands={commands}
    >
      <Outlet context={me} />
    </AppShell>
  );
}
