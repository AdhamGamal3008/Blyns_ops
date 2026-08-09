// Marquee — an infinite horizontal ribbon (used by the Configurable section's
// "Every field · Every workflow …" band). Two identical groups scroll -50% on a
// CSS animation; pauses on hover and under reduced motion.

import type { ReactNode } from "react";
import { useReducedMotion } from "framer-motion";
import styles from "./Marquee.module.css";

type MarqueeProps = {
  children: ReactNode;
  /** Seconds for one full loop; lower = faster. */
  speed?: number;
  reverse?: boolean;
  className?: string;
};

export function Marquee({ children, speed = 42, reverse = false, className }: MarqueeProps) {
  const reduce = useReducedMotion();
  return (
    <div className={`${styles.viewport} ${className ?? ""}`} data-reduce={reduce ? "" : undefined}>
      <div
        className={styles.track}
        style={{ animationDuration: `${speed}s`, animationDirection: reverse ? "reverse" : "normal" }}
      >
        <div className={styles.group}>{children}</div>
        <div className={styles.group} aria-hidden="true">{children}</div>
      </div>
    </div>
  );
}
