import { Building2, Inbox, LayoutDashboard, LogOut, ShieldBan } from "lucide-react";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { adminLogout, adminMe } from "../shared/auth";
import { AppShell, type CommandItem, RouteTransition, type ShellNavItem } from "../shared/shell";
import type { AdminMe } from "../shared/types";
import { Spinner } from "../shared/ui/Spinner/Spinner";

const BASE_NAV: ShellNavItem[] = [
  {
    key: "dashboard",
    label: "Platform dashboard",
    to: "/admin",
    end: true,
    icon: <LayoutDashboard size={20} />,
  },
  { key: "companies", label: "Companies", to: "/admin/companies", icon: <Building2 size={20} /> },
];

// Discovery-session bookings from the landing page. VIEW (1) is the floor to open
// the panel (its list is VIEW-gated), so hide it for admins with no `leads` grant.
const LEADS_NAV: ShellNavItem = {
  key: "leads",
  label: "Discovery Sessions",
  to: "/admin/discovery-bookings",
  icon: <Inbox size={20} />,
};

// Level.READ (2) is the floor to open the IP access panel (its list is READ-gated),
// so hide the nav entry for admins who couldn't use it anyway.
const IP_RULES_NAV: ShellNavItem = {
  key: "ip-rules",
  label: "IP access",
  to: "/admin/ip-rules",
  icon: <ShieldBan size={20} />,
};

function navFor(me: AdminMe): ShellNavItem[] {
  const nav = [...BASE_NAV];
  if ((me.role.permissions.leads ?? 0) >= 1) nav.push(LEADS_NAV);
  if ((me.role.permissions.ip_rules ?? 0) >= 2) nav.push(IP_RULES_NAV);
  return nav;
}

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

  const nav = navFor(me);
  const current = nav.find((n) =>
    n.end ? location.pathname === n.to : location.pathname.startsWith(n.to),
  );
  const title = current?.label ?? "Control plane";

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
      brand={{ title: "Admin Portal", subtitle: "Control plane" }}
      nav={nav}
      user={{ name: me.name, role: me.role.name }}
      onSignOut={() => void logout()}
      title={title}
      breadcrumbs={[{ label: title }]}
      commands={commands}
    >
      <RouteTransition context={me} />
    </AppShell>
  );
}
