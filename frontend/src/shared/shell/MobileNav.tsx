import * as RadixDialog from "@radix-ui/react-dialog";
import { AnimatePresence, motion } from "framer-motion";
import { contentTransition, overlayTransition, useReducedMotion } from "../motion";
import { LogOut, X } from "lucide-react";
import { NavLink } from "react-router-dom";
import { cn } from "../ui/_internal/cn";
import type { ShellNavItem, ShellUser } from "./types";
import styles from "./MobileNav.module.css";

export interface MobileNavProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  brand: { title: string; subtitle?: string };
  nav: ShellNavItem[];
  /** Subset shown in the bottom tab bar (client app). */
  tabs?: ShellNavItem[];
  user: ShellUser;
  onSignOut: () => void;
}

export function MobileNav({
  open,
  onOpenChange,
  brand,
  nav,
  tabs,
  user,
  onSignOut,
}: MobileNavProps) {
  const reduce = useReducedMotion();

  return (
    <>
      <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
        <AnimatePresence>
          {open && (
            <RadixDialog.Portal forceMount>
              <RadixDialog.Overlay asChild forceMount>
                <motion.div
                  className={styles.overlay}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={overlayTransition(reduce)}
                />
              </RadixDialog.Overlay>
              <RadixDialog.Content asChild forceMount>
                <motion.div
                  className={styles.drawer}
                  initial={reduce ? { opacity: 0 } : { x: "-100%" }}
                  animate={reduce ? { opacity: 1 } : { x: 0 }}
                  exit={reduce ? { opacity: 0 } : { x: "-100%" }}
                  transition={contentTransition(reduce)}
                >
                  <div className={styles.drawerHead}>
                    <div className={styles.brand}>
                      <span className={styles.mark} aria-hidden="true">
                        {brand.title.trim().slice(0, 2).toUpperCase()}
                      </span>
                      <span className={styles.brandText}>
                        <RadixDialog.Title className={styles.brandTitle}>
                          {brand.title}
                        </RadixDialog.Title>
                        {brand.subtitle && <span className={styles.brandSub}>{brand.subtitle}</span>}
                      </span>
                    </div>
                    <RadixDialog.Close className={styles.close} aria-label="Close navigation">
                      <X size={18} />
                    </RadixDialog.Close>
                  </div>

                  <nav className={styles.drawerNav} aria-label="Primary">

                    {nav.map((item) => (
                      <NavLink
                        key={item.key}
                        to={item.to}
                        end={item.end}
                        onClick={() => onOpenChange(false)}
                        className={({ isActive }) =>
                          cn(styles.drawerLink, isActive && styles.drawerLinkActive)
                        }
                      >
                        <span className={styles.linkIcon} aria-hidden="true">
                          {item.icon}
                        </span>
                        {item.label}
                      </NavLink>
                    ))}
                  </nav>

                  <div className={styles.drawerFooter}>
                    <div className={styles.user}>
                      <span className={styles.userName}>{user.name}</span>
                      <span className={styles.userRole}>{user.role}</span>
                    </div>
                    <button type="button" className={styles.signOut} onClick={onSignOut}>
                      <LogOut size={16} />
                      Sign out
                    </button>
                  </div>
                </motion.div>
              </RadixDialog.Content>
            </RadixDialog.Portal>
          )}
        </AnimatePresence>
      </RadixDialog.Root>

      {tabs && tabs.length > 0 && (
        <nav className={styles.tabBar} aria-label="Primary">
          {tabs.map((item) => (
            <NavLink
              key={item.key}
              to={item.to}
              end={item.end}
              className={({ isActive }) => cn(styles.tab, isActive && styles.tabActive)}
            >
              <span className={styles.tabIcon} aria-hidden="true">
                {item.icon}
              </span>
              <span className={styles.tabLabel}>{item.label}</span>
            </NavLink>
          ))}
        </nav>
      )}
    </>
  );
}
