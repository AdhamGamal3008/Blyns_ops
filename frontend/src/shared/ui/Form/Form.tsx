import type { ReactNode } from "react";
import { cn } from "../_internal/cn";
import styles from "./Form.module.css";

export function FormSection({
  title,
  description,
  children,
  className,
}: {
  title?: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn(styles.section, className)}>
      {(title != null || description != null) && (
        <div className={styles.sectionHead}>
          {title != null && <h3 className={styles.sectionTitle}>{title}</h3>}
          {description != null && <p className={styles.sectionDesc}>{description}</p>}
        </div>
      )}
      <div className={styles.fields}>{children}</div>
    </section>
  );
}

export function FormGrid({
  columns = 2,
  children,
  className,
}: {
  columns?: 1 | 2;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn(styles.grid, columns === 2 && styles.grid2, className)}>{children}</div>
  );
}

export function FormActions({
  children,
  sticky,
  className,
}: {
  children: ReactNode;
  /** Pins the bar to the bottom of the scroll container for long forms. */
  sticky?: boolean;
  className?: string;
}) {
  return <div className={cn(styles.actions, sticky && styles.sticky, className)}>{children}</div>;
}
