import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../_internal/cn";
import styles from "./KpiCard.module.css";

export interface KpiDelta {
  value: string;
  direction: "up" | "down" | "flat";
  /** When true, a downward move is the good outcome (e.g. overdue invoices falling). */
  invertColor?: boolean;
}

export interface KpiCardProps {
  label: ReactNode;
  value: ReactNode;
  delta?: KpiDelta;
  icon?: ReactNode;
  hint?: ReactNode;
  className?: string;
}

function Delta({ value, direction, invertColor }: KpiDelta) {
  const tone =
    direction === "flat" ? "flat" : (direction === "up") !== Boolean(invertColor) ? "good" : "bad";
  const Icon = direction === "up" ? ArrowUpRight : direction === "down" ? ArrowDownRight : Minus;
  return (
    <span className={cn(styles.delta, styles[`delta_${tone}`])}>
      <Icon size={14} aria-hidden="true" />
      {value}
    </span>
  );
}

export function KpiCard({ label, value, delta, icon, hint, className }: KpiCardProps) {
  return (
    <div className={cn(styles.root, className)}>
      <div className={styles.head}>
        <span className={styles.label}>{label}</span>
        {icon != null && (
          <span className={styles.icon} aria-hidden="true">
            {icon}
          </span>
        )}
      </div>
      <div className={styles.value}>{value}</div>
      {(delta || hint != null) && (
        <div className={styles.foot}>
          {delta && <Delta {...delta} />}
          {hint != null && <span className={styles.hint}>{hint}</span>}
        </div>
      )}
    </div>
  );
}
