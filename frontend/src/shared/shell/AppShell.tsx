import { useCallback, useEffect, useState, type ReactNode } from "react";
import type { BreadcrumbItem } from "../ui/Breadcrumb/Breadcrumb";
import { cn } from "../ui/_internal/cn";
import { CommandPalette } from "./CommandPalette";
import { MobileNav } from "./MobileNav";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import type { CommandItem, ShellNavItem, ShellUser } from "./types";
import styles from "./AppShell.module.css";

const COLLAPSE_KEY = "blyns-sidebar-collapsed";

export interface AppShellProps {
  brand: {
    title: string;
    subtitle?: string;
    /** Company logo (data URI or URL); falls back to a monogram when absent. */
    logo?: string | null;
  };
  nav: ShellNavItem[];
  user: ShellUser;
  onSignOut: () => void;
  title: string;
  breadcrumbs?: BreadcrumbItem[];
  commands: CommandItem[];
  /** Bottom tab bar destinations for mobile (client app). */
  mobileTabs?: ShellNavItem[];
  /** Optional top-bar slot before the user menu (e.g. a reminders bell). */
  notifications?: ReactNode;
  children: ReactNode;
}

export function AppShell({
  brand,
  nav,
  user,
  onSignOut,
  title,
  breadcrumbs,
  commands,
  mobileTabs,
  notifications,
  children,
}: AppShellProps) {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(COLLAPSE_KEY) === "1";
    } catch {
      return false;
    }
  });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  const toggleCollapse = useCallback(() => {
    setCollapsed((c) => {
      const next = !c;
      try {
        localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className={styles.root}>
      {/* first in the tab order: a keyboard user skips the whole sidebar to the
          page content, which otherwise takes a dozen tabs to get past */}
      <a href="#main-content" className={styles.skipLink}>
        Skip to content
      </a>

      <div className={styles.sidebar}>
        <Sidebar
          brand={brand}
          nav={nav}
          collapsed={collapsed}
          onToggleCollapse={toggleCollapse}
        />
      </div>

      <div className={styles.main}>
        <TopBar
          title={title}
          breadcrumbs={breadcrumbs}
          user={user}
          onSignOut={onSignOut}
          onOpenPalette={() => setPaletteOpen(true)}
          onOpenDrawer={() => setDrawerOpen(true)}
          notifications={notifications}
        />
        <main
          id="main-content"
          // tabindex -1 so the skip link can move focus here without making the
          // region itself a tab stop
          tabIndex={-1}
          aria-label={title}
          className={cn(styles.content, mobileTabs && styles.hasTabs)}
        >
          {children}
        </main>
      </div>

      <MobileNav
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        brand={brand}
        nav={nav}
        tabs={mobileTabs}
        user={user}
        onSignOut={onSignOut}
      />

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} commands={commands} />
    </div>
  );
}
