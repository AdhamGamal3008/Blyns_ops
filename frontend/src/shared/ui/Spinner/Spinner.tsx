import { cn } from "../_internal/cn";
import styles from "./Spinner.module.css";

export interface SpinnerProps {
  size?: "sm" | "md" | "lg";
  /** Accessible label; announced to screen readers. */
  label?: string;
  className?: string;
}

export function Spinner({ size = "md", label = "Loading", className }: SpinnerProps) {
  return (
    <span
      className={cn(styles.root, styles[size], className)}
      role="status"
      aria-label={label}
    />
  );
}
