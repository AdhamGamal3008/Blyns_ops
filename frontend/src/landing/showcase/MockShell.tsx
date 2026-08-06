// A static, non-interactive stand-in for the client-portal shell (sidebar +
// topbar), used only to frame the marketing "screenshots". Deliberately NOT the
// real AppShell: that registers global listeners (⌘K command palette, etc.) we
// must never attach on the landing page. Pure presentational markup here.

import { Contact, FolderKanban, LayoutDashboard, Package, Receipt, Settings } from "lucide-react";
import type { ReactNode } from "react";
import styles from "./MockShell.module.css";

const NAV = [
  { key: "leadership", label: "Dashboard", icon: LayoutDashboard },
  { key: "projects", label: "Projects", icon: FolderKanban },
  { key: "clients", label: "CRM", icon: Contact },
  { key: "inventory", label: "Inventory", icon: Package },
  { key: "finance", label: "Finance", icon: Receipt },
  { key: "settings", label: "Settings", icon: Settings },
] as const;

// Screens that live under another module's nav highlight it instead.
const ACTIVE_ALIAS: Record<string, string> = { operations: "projects" };

export function MockShell({ active, children }: { active: string; children: ReactNode }) {
  const activeKey = ACTIVE_ALIAS[active] ?? active;
  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <span className={styles.brandMark}>O</span>
          <div>
            <div className={styles.brandName}>Oakwood Interiors</div>
            <div className={styles.brandSub}>Blyns workspace</div>
          </div>
        </div>
        <nav className={styles.nav}>
          {NAV.map(({ key, label, icon: Icon }) => (
            <span key={key} className={key === activeKey ? styles.navItemActive : styles.navItem}>
              <Icon size={18} strokeWidth={1.75} />
              {label}
            </span>
          ))}
        </nav>
        <div className={styles.user}>
          <span className={styles.avatar}>AG</span>
          <div>
            <div className={styles.userName}>Adham Gamal</div>
            <div className={styles.userRole}>Operations lead</div>
          </div>
        </div>
      </aside>

      <div className={styles.main}>
        <div className={styles.topbar}>
          <span className={styles.search}>Search projects, clients, invoices…</span>
          <span className={styles.avatar}>AG</span>
        </div>
        <div className={styles.content}>{children}</div>
      </div>
    </div>
  );
}
