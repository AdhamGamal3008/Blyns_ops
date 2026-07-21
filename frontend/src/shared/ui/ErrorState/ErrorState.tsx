import { TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "../Button/Button";
import { cn } from "../_internal/cn";
import styles from "./ErrorState.module.css";

export interface ErrorStateProps {
  title?: ReactNode;
  description?: ReactNode;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
}

export function ErrorState({
  title = "Something went wrong",
  description = "We couldn't load this. Check your connection and try again.",
  onRetry,
  retryLabel = "Try again",
  className,
}: ErrorStateProps) {
  return (
    <div className={cn(styles.root, className)} role="alert">
      <span className={styles.icon} aria-hidden="true">
        <TriangleAlert size={24} />
      </span>
      <p className={styles.title}>{title}</p>
      {description != null && <p className={styles.description}>{description}</p>}
      {onRetry && (
        <div className={styles.action}>
          <Button variant="secondary" onClick={onRetry}>
            {retryLabel}
          </Button>
        </div>
      )}
    </div>
  );
}
