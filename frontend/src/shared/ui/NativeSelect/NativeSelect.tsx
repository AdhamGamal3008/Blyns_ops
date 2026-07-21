// A real <select> wearing the kit's Select styling.
//
// The Radix Select is the default — it renders a styled listbox and matches the
// rest of the kit. This one exists for the places where a native control is the
// better control: dense repeating rows (a kanban card, a table cell) where a
// portalled popover is heavy, and mobile, where the OS picker beats any custom
// menu. Same visual language either way.

import { forwardRef, type SelectHTMLAttributes } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "../_internal/cn";
import type { SelectOption } from "../Select/Select";
import styles from "./NativeSelect.module.css";

export interface NativeSelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  options: SelectOption[];
  selectSize?: "md" | "compact";
  invalid?: boolean;
}

export const NativeSelect = forwardRef<HTMLSelectElement, NativeSelectProps>(
  function NativeSelect({ options, selectSize = "md", invalid, className, ...rest }, ref) {
    return (
      <span className={cn(styles.wrap, className)}>
        <select
          ref={ref}
          className={cn(styles.select, styles[selectSize])}
          data-invalid={invalid || undefined}
          aria-invalid={invalid || undefined}
          {...rest}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value} disabled={opt.disabled}>
              {typeof opt.label === "string" ? opt.label : opt.value}
            </option>
          ))}
        </select>
        <ChevronDown size={16} className={styles.icon} aria-hidden="true" />
      </span>
    );
  },
);
