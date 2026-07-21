import { forwardRef, type HTMLAttributes, type ReactNode } from "react";
import { cn } from "../_internal/cn";
import styles from "./Card.module.css";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Adds hover elevation + a focus ring; use for clickable cards. */
  interactive?: boolean;
  /** Inner padding (default true). Turn off for edge-to-edge media/tables. */
  padded?: boolean;
}

export const Card = forwardRef<HTMLDivElement, CardProps>(function Card(
  { interactive, padded = true, className, children, ...rest },
  ref,
) {
  return (
    <div
      ref={ref}
      className={cn(styles.root, padded && styles.padded, interactive && styles.interactive, className)}
      tabIndex={interactive ? 0 : undefined}
      {...rest}
    >
      {children}
    </div>
  );
});

export interface CardHeaderProps {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
}

export function CardHeader({ title, description, actions, children, className }: CardHeaderProps) {
  return (
    <header className={cn(styles.header, className)}>
      <div className={styles.headingGroup}>
        {title != null && <h3 className={styles.title}>{title}</h3>}
        {/* See PageHeader: a description may hold chips, so it cannot be a <p>. */}
        {description != null && <div className={styles.description}>{description}</div>}
        {children}
      </div>
      {actions != null && <div className={styles.actions}>{actions}</div>}
    </header>
  );
}

export function CardFooter({ children, className }: { children: ReactNode; className?: string }) {
  return <footer className={cn(styles.footer, className)}>{children}</footer>;
}
