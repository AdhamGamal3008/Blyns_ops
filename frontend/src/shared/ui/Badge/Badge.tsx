import type { ReactNode } from "react";
import { cn } from "../_internal/cn";
import styles from "./Badge.module.css";

export type BadgeTone = "neutral" | "brand" | "success" | "warning" | "danger" | "info";
export type BadgeVariant = "soft" | "solid" | "outline";

export interface BadgeProps {
  children: ReactNode;
  tone?: BadgeTone;
  variant?: BadgeVariant;
  /** Leading status dot in the current color. */
  dot?: boolean;
  className?: string;
}

export function Badge({
  children,
  tone = "neutral",
  variant = "soft",
  dot,
  className,
}: BadgeProps) {
  return (
    <span className={cn(styles.root, styles[tone], styles[variant], className)}>
      {dot && <span className={styles.dot} aria-hidden="true" />}
      {children}
    </span>
  );
}
