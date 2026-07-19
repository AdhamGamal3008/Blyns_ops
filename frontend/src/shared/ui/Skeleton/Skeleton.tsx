import type { CSSProperties } from "react";
import { cn } from "../_internal/cn";
import styles from "./Skeleton.module.css";

export interface SkeletonProps {
  variant?: "text" | "rect" | "circle";
  width?: number | string;
  height?: number | string;
  /** Number of stacked lines (text variant). */
  lines?: number;
  className?: string;
}

export function Skeleton({ variant = "rect", width, height, lines = 1, className }: SkeletonProps) {
  const style: CSSProperties = { width, height };

  if (variant === "text" && lines > 1) {
    return (
      <span className={styles.stack} aria-hidden="true">
        {Array.from({ length: lines }).map((_, i) => (
          <span
            key={i}
            className={cn(styles.root, styles.text, className)}
            style={{ width: i === lines - 1 ? "70%" : width ?? "100%" }}
          />
        ))}
      </span>
    );
  }

  return (
    <span
      className={cn(styles.root, styles[variant], className)}
      style={style}
      aria-hidden="true"
    />
  );
}
