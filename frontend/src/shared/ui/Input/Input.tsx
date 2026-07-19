import { forwardRef, type InputHTMLAttributes, type ReactNode } from "react";
import { cn } from "../_internal/cn";
import styles from "./Input.module.css";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
  /** Named to avoid clashing with the native numeric `size` attribute. */
  inputSize?: "md" | "compact";
  iconLeft?: ReactNode;
  iconRight?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  {
    invalid,
    inputSize = "md",
    iconLeft,
    iconRight,
    className,
    disabled,
    "aria-invalid": ariaInvalid,
    ...rest
  },
  ref,
) {
  const isInvalid = invalid ?? (ariaInvalid === true || ariaInvalid === "true");
  return (
    <span
      className={cn(styles.wrap, styles[inputSize], disabled && styles.disabled, className)}
      data-invalid={isInvalid || undefined}
    >
      {iconLeft && (
        <span className={styles.icon} aria-hidden="true">
          {iconLeft}
        </span>
      )}
      <input
        ref={ref}
        className={styles.input}
        disabled={disabled}
        aria-invalid={isInvalid || undefined}
        {...rest}
      />
      {iconRight && (
        <span className={styles.icon} aria-hidden="true">
          {iconRight}
        </span>
      )}
    </span>
  );
});
