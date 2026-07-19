import * as Label from "@radix-ui/react-label";
import { cloneElement, isValidElement, useId, type ReactElement, type ReactNode } from "react";
import { cn } from "../_internal/cn";
import styles from "./Field.module.css";

export interface FieldProps {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  required?: boolean;
  /** The control. Its id / aria-invalid / aria-describedby are wired automatically. */
  children: ReactNode;
  id?: string;
  className?: string;
}

export function Field({ label, hint, error, required, children, id: idProp, className }: FieldProps) {
  const reactId = useId();
  const id = idProp ?? reactId;
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const describedBy = error ? errorId : hint ? hintId : undefined;

  const control = isValidElement(children)
    ? cloneElement(children as ReactElement<Record<string, unknown>>, {
        id,
        "aria-invalid": error ? true : undefined,
        "aria-describedby": describedBy,
      })
    : children;

  return (
    <div className={cn(styles.root, className)}>
      {label != null && (
        <Label.Root className={styles.label} htmlFor={id}>
          {label}
          {required && (
            <span className={styles.required} aria-hidden="true">
              *
            </span>
          )}
        </Label.Root>
      )}
      {control}
      {error != null ? (
        <p id={errorId} className={styles.error}>
          {error}
        </p>
      ) : hint != null ? (
        <p id={hintId} className={styles.hint}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}
