import { ChevronDown, LogOut, Menu, Search } from "lucide-react";
import type { ReactNode } from "react";
import { Avatar } from "../ui/Avatar/Avatar";
import { Breadcrumb, type BreadcrumbItem } from "../ui/Breadcrumb/Breadcrumb";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/DropdownMenu/DropdownMenu";
import type { ShellUser } from "./types";
import styles from "./TopBar.module.css";

export interface TopBarProps {
  title: string;
  breadcrumbs?: BreadcrumbItem[];
  user: ShellUser;
  onSignOut: () => void;
  onOpenPalette: () => void;
  onOpenDrawer: () => void;
  /** Optional slot in the right cluster, before the user menu — e.g. a
   *  reminders/notifications bell. Kept as a node so the design-system shell
   *  stays router- and data-free; the app supplies the live control. */
  notifications?: ReactNode;
}

function UserMenu({ user, onSignOut }: { user: ShellUser; onSignOut: () => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" className={styles.userBtn}>
          <Avatar name={user.name} size="sm" />
          <span className={styles.userText}>
            <span className={styles.userName}>{user.name}</span>
            <span className={styles.userRole}>{user.role}</span>
          </span>
          <ChevronDown size={16} className={styles.userChevron} aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>{user.name}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem icon={<LogOut size={16} />} tone="danger" onSelect={onSignOut}>
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function TopBar({
  title,
  breadcrumbs,
  user,
  onSignOut,
  onOpenPalette,
  onOpenDrawer,
  notifications,
}: TopBarProps) {
  return (
    <header className={styles.root}>
      <div className={styles.left}>
        <button
          type="button"
          className={styles.hamburger}
          onClick={onOpenDrawer}
          aria-label="Open navigation"
        >
          <Menu size={20} />
        </button>
        {breadcrumbs && breadcrumbs.length > 0 && (
          <div className={styles.breadcrumbs}>
            <Breadcrumb items={breadcrumbs} />
          </div>
        )}
        <h1 className={styles.mobileTitle}>{title}</h1>
      </div>

      <div className={styles.right}>
        <button
          type="button"
          className={styles.paletteBtn}
          onClick={onOpenPalette}
          aria-label="Open command palette"
        >
          <Search size={16} aria-hidden="true" />
          <span className={styles.paletteLabel}>Search</span>
          <kbd className={styles.kbd}>⌘K</kbd>
        </button>
        {notifications}
        <div className={styles.userMenu}>
          <UserMenu user={user} onSignOut={onSignOut} />
        </div>
      </div>
    </header>
  );
}
