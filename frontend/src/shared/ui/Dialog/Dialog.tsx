import * as RadixDialog from "@radix-ui/react-dialog";
import { AnimatePresence, motion } from "framer-motion";
import { contentTransition, overlayTransition, useReducedMotion } from "../../motion";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../_internal/cn";
import styles from "./Dialog.module.css";

export interface ModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg";
}

export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  size = "md",
}: ModalProps) {
  const reduce = useReducedMotion();
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
                transition={overlayTransition(reduce)}
              />
            </RadixDialog.Overlay>
            <div className={styles.positioner}>
              <RadixDialog.Content asChild forceMount>
                <motion.div
                  className={cn(styles.content, styles[size])}
                  initial={reduce ? { opacity: 0 } : { opacity: 0, y: 12, scale: 0.98 }}
                  animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
                  exit={reduce ? { opacity: 0 } : { opacity: 0, y: 8, scale: 0.98 }}
                  transition={contentTransition(reduce)}
                >
                  <div className={styles.header}>
                    <div className={styles.headingGroup}>
                      <RadixDialog.Title className={styles.title}>{title}</RadixDialog.Title>
                      {description != null && (
                        <RadixDialog.Description className={styles.description}>
                          {description}
                        </RadixDialog.Description>
                      )}
                    </div>
                    <RadixDialog.Close className={styles.close} aria-label="Close">
                      <X size={18} />
                    </RadixDialog.Close>
                  </div>
                  {children != null && <div className={styles.body}>{children}</div>}
                  {footer != null && <div className={styles.footer}>{footer}</div>}
                </motion.div>
              </RadixDialog.Content>
            </div>
          </RadixDialog.Portal>
        )}
      </AnimatePresence>
    </RadixDialog.Root>
  );
}
