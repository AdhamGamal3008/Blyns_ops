import * as RadixCheckbox from "@radix-ui/react-checkbox";
import { Check, Minus } from "lucide-react";
import { useId, type ComponentPropsWithoutRef, type ReactNode } from "react";
import { cn } from "../_internal/cn";
import styles from "./Checkbox.module.css";

export interface CheckboxProps extends ComponentPropsWithoutRef<typeof RadixCheckbox.Root> {
  label?: ReactNode;
}

export function Checkbox({ label, className, id, checked, ...props }: CheckboxProps) {
  const reactId = useId();
  const cid = id ?? reactId;
  return (
    <div className={cn(styles.row, className)}>
      <RadixCheckbox.Root id={cid} className={styles.box} checked={checked} {...props}>
        <RadixCheckbox.Indicator className={styles.indicator}>
          {checked === "indeterminate" ? <Minus size={14} strokeWidth={3} /> : <Check size={14} strokeWidth={3} />}
        </RadixCheckbox.Indicator>
      </RadixCheckbox.Root>
      {label != null && (
        <label htmlFor={cid} className={styles.label}>
          {label}
        </label>
      )}
    </div>
  );
}
