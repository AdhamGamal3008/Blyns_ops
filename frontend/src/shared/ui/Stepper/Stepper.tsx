import { Check } from "lucide-react";
import { cn } from "../_internal/cn";
import styles from "./Stepper.module.css";

export interface Step {
  key: string;
  label: string;
  description?: string;
}

export interface StepperProps {
  steps: Step[];
  /** Index of the active step. Earlier steps render as complete. */
  current: number;
  orientation?: "horizontal" | "vertical";
  className?: string;
}

export function Stepper({ steps, current, orientation = "horizontal", className }: StepperProps) {
  return (
    <ol className={cn(styles.root, styles[orientation], className)}>
      {steps.map((step, i) => {
        const state = i < current ? "complete" : i === current ? "current" : "upcoming";
        return (
          <li
            key={step.key}
            className={cn(styles.step, styles[state])}
            aria-current={state === "current" ? "step" : undefined}
          >
            <div className={styles.marker}>
              <span className={styles.circle}>
                {state === "complete" ? <Check size={16} strokeWidth={3} /> : i + 1}
              </span>
              {i < steps.length - 1 && <span className={styles.connector} />}
            </div>
            <div className={styles.body}>
              <span className={styles.label}>{step.label}</span>
              {step.description && <span className={styles.description}>{step.description}</span>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
