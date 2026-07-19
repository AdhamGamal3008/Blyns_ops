import { forwardRef, type TextareaHTMLAttributes } from "react";
import { cn } from "../_internal/cn";
import styles from "./Textarea.module.css";

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { invalid, className, "aria-invalid": ariaInvalid, ...rest },
  ref,
) {
  const isInvalid = invalid ?? (ariaInvalid === true || ariaInvalid === "true");
  return (
    <textarea
      ref={ref}
      className={cn(styles.root, className)}
      aria-invalid={isInvalid || undefined}
      {...rest}
    />
  );
});
