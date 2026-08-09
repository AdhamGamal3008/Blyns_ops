// PillLink — the landing's call-to-action anchor: a rounded pill with a trailing
// arrow that extends on hover, wrapped in a magnetic field. Two looks: a solid
// ivory "primary" and a hairline "ghost".

import type { ReactNode } from "react";
import { Magnetic } from "../motion/Magnetic";
import styles from "./PillLink.module.css";

type PillLinkProps = {
  href: string;
  children: ReactNode;
  variant?: "primary" | "ghost";
  className?: string;
};

export function PillLink({ href, children, variant = "primary", className }: PillLinkProps) {
  return (
    <Magnetic className={`${styles.magnet} ${className ?? ""}`} strength={0.25}>
      <a href={href} className={`${styles.pill} ${styles[variant]}`}>
        <span className={styles.text}>{children}</span>
        <span className={styles.arrow} aria-hidden="true">
          <svg viewBox="0 0 24 8" width="24" height="8" fill="none">
            <path d="M0 4h22M19 1l3 3-3 3" stroke="currentColor" strokeWidth="1.2" />
          </svg>
        </span>
      </a>
    </Magnetic>
  );
}
