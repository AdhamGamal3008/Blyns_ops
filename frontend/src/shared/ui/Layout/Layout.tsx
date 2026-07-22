// Layout primitives shared by every module screen, so page composition is
// tokens + a class instead of a bespoke style object per screen.

import type { CSSProperties, ReactNode } from "react";
import { staggerStyles, useFirstPaint } from "../../motion";
import { cn } from "../_internal/cn";
import styles from "./Layout.module.css";

type SpaceToken = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;

const space = (n: SpaceToken) => `var(--sp-${n})`;

export interface StackProps {
  gap?: SpaceToken;
  children: ReactNode;
  className?: string;
}

/** Vertical rhythm for a page or a card body. */
export function Stack({ gap = 5, children, className }: StackProps) {
  return (
    <div
      className={cn(styles.stack, className)}
      style={{ "--stack-gap": space(gap) } as CSSProperties}
    >
      {children}
    </div>
  );
}

export interface GridProps {
  /** Minimum column width before the grid drops a column. */
  min?: number;
  gap?: SpaceToken;
  /** First-paint entrance for the tiles. Off for grids of bare form fields. */
  stagger?: boolean;
  children: ReactNode;
  className?: string;
}

/** Auto-fitting card grid — KPI rows, tile groups, form card sets. */
export function Grid({ min = 220, gap = 4, stagger = true, children, className }: GridProps) {
  // tiles land in sequence on first paint, then the grid is inert
  const firstPaint = useFirstPaint();
  const animate = stagger && firstPaint;
  return (
    <div
      className={cn(styles.grid, animate && staggerStyles.staggerChildren, className)}
      style={{ "--grid-min": `${min}px`, "--grid-gap": space(gap) } as CSSProperties}
    >
      {children}
    </div>
  );
}

export interface SplitProps {
  /** Width of the secondary column on desktop. */
  asideWidth?: number;
  /** Render the aside on the left instead of the right. */
  asideFirst?: boolean;
  children: ReactNode;
  className?: string;
}

/** Main column + companion rail; collapses to one column under 1024px. */
export function Split({ asideWidth = 340, asideFirst, children, className }: SplitProps) {
  return (
    <div
      className={cn(styles.split, asideFirst && styles.splitAsideFirst, className)}
      style={{ "--split-aside": `${asideWidth}px` } as CSSProperties}
    >
      {children}
    </div>
  );
}

export interface RowProps {
  gap?: SpaceToken;
  children: ReactNode;
  className?: string;
}

/** Wrapping horizontal group — filter bars, action clusters, badge lists. */
export function Row({ gap = 3, children, className }: RowProps) {
  return (
    <div className={cn(styles.row, className)} style={{ "--row-gap": space(gap) } as CSSProperties}>
      {children}
    </div>
  );
}
