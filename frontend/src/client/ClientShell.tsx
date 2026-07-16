// Tenant shell: sidebar filtered by role map + enabled modules — a module at
// NONE never appears in navigation (docs/AUTH_RBAC.md acceptance).

import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { clientLogout, clientMe } from "../shared/auth";
import type { ClientMe } from "../shared/types";
import { Spinner } from "../shared/ui";

const MODULE_NAV: { key: string; label: string; route: string }[] = [
  { key: "projects", label: "Projects", route: "/app/projects" },
  { key: "crm", label: "CRM", route: "/app/crm" },
  { key: "inventory", label: "Inventory", route: "/app/inventory" },
  { key: "finance", label: "Finance", route: "/app/finance" },
  { key: "settings", label: "Settings", route: "/app/settings" },
];

export function ClientShell() {
  const navigate = useNavigate();
  const [me, setMe] = useState<ClientMe | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    clientMe().then(setMe).catch(() => setError(true));
  }, []);

  useEffect(() => {
    if (error) navigate("/login");
  }, [error, navigate]);

  if (!me) return <Spinner />;

  const visible = MODULE_NAV.filter(
    (m) =>
      me.company.enabled_modules.includes(m.key) &&
      (me.role.permissions[m.key] ?? 0) >= 1, // ≥ VIEW
  );

  async function logout() {
    await clientLogout();
    navigate("/login");
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          {me.company.name}
          <small>Blyns ERP workspace</small>
        </div>
        <NavLink to="/app" end className={({ isActive }) =>
          `nav-item ${isActive ? "active" : ""}`}>
          Dashboard
        </NavLink>
        {visible.map((m) => (
          <NavLink key={m.key} to={m.route} className={({ isActive }) =>
            `nav-item ${isActive ? "active" : ""}`}>
            {m.label}
          </NavLink>
        ))}
        <div className="spacer" />
        <button className="nav-item" style={{ background: "none", border: 0, cursor: "pointer", font: "inherit", textAlign: "left" }}
          onClick={logout}>
          Sign out
        </button>
      </aside>
      <div className="main">
        <header className="topbar">
          <h2 style={{ fontSize: 16 }}>Dashboard</h2>
          <span className="who">
            <b>{me.name}</b> · {me.role.name}
          </span>
        </header>
        <div className="content">
          <Outlet context={me} />
        </div>
      </div>
    </div>
  );
}
