// Section — the shared shell every content section sits in: an id anchor, a tone
// (subtle warm-black shifts + a top hairline for rhythm), consistent vertical
// padding, and nav-clearing scroll-margin. Children own their own `.l-container`
// so a section can also go full-bleed (e.g. the Configurable marquee).

import type { ReactNode } from "react";
import styles from "./Section.module.css";

type SectionProps = {
  id: string;
  tone?: "base" | "raised" | "deep";
  children: ReactNode;
  className?: string;
  labelledBy?: string;
};

export function Section({ id, tone = "base", children, className, labelledBy }: SectionProps) {
  return (
    <section
      id={id}
      className={`${styles.section} ${styles[tone]} ${className ?? ""}`}
      aria-labelledby={labelledBy}
    >
      {children}
    </section>
  );
}
