// A utilisation bar for a bounded quantity — CPU, disk, seats used.
//
// The threshold tone is a secondary encoding only: the value is always rendered
// as text beside it, so the state is never carried by colour alone. Uses the
// reserved status tokens, which is why Meter never accepts an arbitrary colour.

import { cn } from "../_internal/cn";
import styles from "./Meter.module.css";

export interface MeterProps {
  /** Current value, in the same unit as `max`. */
  value: number;
  max?: number;
  /** Fraction of max at which the bar turns ochre / oxblood. */
  warnAt?: number;
  dangerAt?: number;
  /** Accessible name — required, since the bar itself carries no text. */
  label: string;
  className?: string;
}

export function Meter({
  value,
  max = 100,
  warnAt = 0.75,
  dangerAt = 0.9,
  label,
  className,
}: MeterProps) {
  const ratio = max > 0 ? value / max : 0;
  const tone = ratio >= dangerAt ? "danger" : ratio >= warnAt ? "warn" : "ok";

  return (
    <div
      className={cn(styles.track, styles[tone], className)}
      role="meter"
      aria-label={label}
      aria-valuenow={Math.round(value)}
      aria-valuemin={0}
      aria-valuemax={max}
    >
      <div className={styles.fill} style={{ inlineSize: `${Math.min(ratio, 1) * 100}%` }} />
    </div>
  );
}
