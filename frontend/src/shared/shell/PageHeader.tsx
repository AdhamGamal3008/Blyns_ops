import type { ReactNode } from "react";
import { cn } from "../ui/_internal/cn";
import styles from "./PageHeader.module.css";

export interface PageHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  /** Primary action(s), e.g. a Button. */
  actions?: ReactNode;
  className?: string;
}

export function PageHeader({ title, description, actions, className }: PageHeaderProps) {
  return (
    <div className={cn(styles.root, className)}>
      <div className={styles.text}>
        <h1 className={styles.title}>{title}</h1>
        {/* A div, not a p: page descriptions routinely carry badges and chips,
            and a block element inside a <p> is invalid nesting. */}
        {description != null && <div className={styles.description}>{description}</div>}
      </div>
      {actions != null && <div className={styles.actions}>{actions}</div>}
    </div>
  );
}
