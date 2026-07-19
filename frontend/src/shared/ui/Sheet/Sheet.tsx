import * as RadixDialog from "@radix-ui/react-dialog";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../_internal/cn";
import styles from "./Sheet.module.css";

export interface SheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  side?: "left" | "right";
}

export function Sheet({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  side = "right",
}: SheetProps) {
  const reduce = useReducedMotion();
  const offscreen = side === "right" ? "100%" : "-100%";
  return (
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
                transition={{ duration: reduce ? 0 : 0.18 }}
              />
            </RadixDialog.Overlay>
            <RadixDialog.Content asChild forceMount>
              <motion.div
                className={cn(styles.panel, styles[side])}
                initial={reduce ? { opacity: 0 } : { x: offscreen }}
                animate={reduce ? { opacity: 1 } : { x: 0 }}
                exit={reduce ? { opacity: 0 } : { x: offscreen }}
                transition={{ duration: reduce ? 0 : 0.28, ease: [0.2, 0, 0, 1] }}
              >
                <div className={styles.header}>
                  <RadixDialog.Title className={styles.title}>{title}</RadixDialog.Title>
                  <RadixDialog.Close className={styles.close} aria-label="Close">
                    <X size={18} />
                  </RadixDialog.Close>
                </div>
                {description != null && (
                  <RadixDialog.Description className={styles.description}>
                    {description}
                  </RadixDialog.Description>
                )}
                <div className={styles.body}>{children}</div>
                {footer != null && <div className={styles.footer}>{footer}</div>}
              </motion.div>
            </RadixDialog.Content>
          </RadixDialog.Portal>
        )}
      </AnimatePresence>
    </RadixDialog.Root>
  );
}
