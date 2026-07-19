import { CircleAlert, CircleCheck, Info, TriangleAlert, X, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../_internal/cn";
import styles from "./Banner.module.css";

export type BannerTone = "info" | "success" | "warning" | "danger" | "neutral";

const icons: Record<BannerTone, LucideIcon> = {
  info: Info,
  success: CircleCheck,
  warning: TriangleAlert,
  danger: CircleAlert,
  neutral: Info,
};

export interface BannerProps {
  tone?: BannerTone;
  title?: ReactNode;
  children?: ReactNode;
  /** Trailing action node (e.g. a Button). */
  action?: ReactNode;
  onDismiss?: () => void;
  className?: string;
}

export function Banner({
  tone = "info",
  title,
  children,
  action,
  onDismiss,
  className,
}: BannerProps) {
  const Icon = icons[tone];
  return (
    <div className={cn(styles.root, styles[tone], className)} role="status">
      <span className={styles.icon} aria-hidden="true">
        <Icon size={20} />
      </span>
      <div className={styles.body}>
        {title != null && <p className={styles.title}>{title}</p>}
        {children != null && <div className={styles.message}>{children}</div>}
      </div>
      {action != null && <div className={styles.action}>{action}</div>}
      {onDismiss && (
        <button type="button" className={styles.dismiss} onClick={onDismiss} aria-label="Dismiss">
          <X size={16} />
        </button>
      )}
    </div>
  );
}
