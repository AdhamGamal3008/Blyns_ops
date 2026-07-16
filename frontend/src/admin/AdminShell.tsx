import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { adminLogout, adminMe } from "../shared/auth";
import type { AdminMe } from "../shared/types";
import { Spinner } from "../shared/ui";

export function AdminShell() {
  const navigate = useNavigate();
  const [me, setMe] = useState<AdminMe | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    adminMe().then(setMe).catch(() => setError(true));
  }, []);

  useEffect(() => {
    if (error) navigate("/admin/login");
  }, [error, navigate]);

  if (!me) return <Spinner />;

  async function logout() {
    await adminLogout();
    navigate("/admin/login");
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          Admin Portal
          <small>Blyns ERP control plane</small>
        </div>
        <NavLink to="/admin" end className={({ isActive }) =>
          `nav-item ${isActive ? "active" : ""}`}>
          Platform dashboard
        </NavLink>
        <NavLink to="/admin/companies" className={({ isActive }) =>
          `nav-item ${isActive ? "active" : ""}`}>
          Companies
        </NavLink>
        <div className="spacer" />
        <button className="nav-item" style={{ background: "none", border: 0, cursor: "pointer", font: "inherit", textAlign: "left" }}
          onClick={logout}>
          Sign out
        </button>
      </aside>
      <div className="main">
        <header className="topbar">
          <h2 style={{ fontSize: 16 }}>Control plane</h2>
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
