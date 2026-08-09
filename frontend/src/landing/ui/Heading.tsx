// Heading — the section display headline in Instrument Serif, with an optional
// second line (`sub`) that reads muted by default or rust-italic for the
// tentpole sections. Pairs with <SectionLabel> above it.

import type { ReactNode } from "react";
import styles from "./Heading.module.css";

type HeadingProps = {
  id?: string;
  children: ReactNode;
  sub?: ReactNode;
  subTone?: "muted" | "rust";
  className?: string;
};

export function Heading({ id, children, sub, subTone = "muted", className }: HeadingProps) {
  return (
    <h2 id={id} className={`${styles.heading} ${className ?? ""}`}>
      {children}
      {sub ? (
        <span className={`${styles.sub} ${subTone === "rust" ? styles.rust : ""}`}>{sub}</span>
      ) : null}
    </h2>
  );
}
