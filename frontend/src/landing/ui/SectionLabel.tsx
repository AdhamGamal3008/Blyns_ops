// SectionLabel — the mono "01 — The approach" micro-heading that opens each
// section, with a small rust index and a hairline tick.

import type { ReactNode } from "react";
import styles from "./SectionLabel.module.css";

type SectionLabelProps = {
  index?: string;
  children: ReactNode;
  className?: string;
};

export function SectionLabel({ index, children, className }: SectionLabelProps) {
  return (
    <p className={`${styles.label} ${className ?? ""}`}>
      <span className={styles.tick} aria-hidden="true" />
      {index ? <span className={styles.index}>{index}</span> : null}
      <span>{children}</span>
    </p>
  );
}
