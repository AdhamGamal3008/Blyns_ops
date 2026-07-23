import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { cn } from "../ui/_internal/cn";
import { Tooltip } from "../ui/Tooltip/Tooltip";
import type { ShellNavItem } from "./types";
import styles from "./Sidebar.module.css";

export interface SidebarProps {
  brand: { title: string; subtitle?: string };
  nav: ShellNavItem[];
  collapsed: boolean;
  onToggleCollapse: () => void;
  footer?: ReactNode;
  /** Called after navigating (used by the mobile drawer to close itself). */
  onNavigate?: () => void;
}

function monogram(title: string): string {
  const parts = title.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return title.trim().slice(0, 2).toUpperCase();
}

function SidebarLink({
  item,
  collapsed,
  onNavigate,
}: {
  item: ShellNavItem;
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const link = (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      className={({ isActive }) => cn(styles.link, isActive && styles.active)}
    >
      <span className={styles.linkIcon} aria-hidden="true">
        {item.icon}
      </span>
      {!collapsed && <span className={styles.linkLabel}>{item.label}</span>}
    </NavLink>
  );
  return collapsed ? (
    <Tooltip content={item.label} side="right">
      {link}
    </Tooltip>
  ) : (
    link
  );
}

export function Sidebar({
  brand,
  nav,
  collapsed,
  onToggleCollapse,
  footer,
  onNavigate,
}: SidebarProps) {
  return (
    <aside className={cn(styles.root, collapsed && styles.collapsed)}>
      <div className={styles.brand}>
        <span className={styles.mark} aria-hidden="true">
          {monogram(brand.title)}
        </span>
        {!collapsed && (
          <span className={styles.brandText}>
            <span className={styles.brandTitle}>{brand.title}</span>
            {brand.subtitle && <span className={styles.brandSub}>{brand.subtitle}</span>}
          </span>
        )}
      </div>

      <nav className={styles.nav} aria-label="Primary">
        {nav.map((item) => (
          <SidebarLink key={item.key} item={item} collapsed={collapsed} onNavigate={onNavigate} />
        ))}
      </nav>

      {footer && <div className={styles.footer}>{footer}</div>}

      <button
        type="button"
        className={styles.collapseBtn}
        onClick={onToggleCollapse}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        <span className={styles.linkIcon} aria-hidden="true">
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </span>
        {!collapsed && <span>Collapse</span>}
      </button>
    </aside>
  );
}
