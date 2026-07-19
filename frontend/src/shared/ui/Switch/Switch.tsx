import * as RadixSwitch from "@radix-ui/react-switch";
import { useId, type ComponentPropsWithoutRef, type ReactNode } from "react";
import { cn } from "../_internal/cn";
import styles from "./Switch.module.css";

export interface SwitchProps extends ComponentPropsWithoutRef<typeof RadixSwitch.Root> {
  label?: ReactNode;
}

export function Switch({ label, className, id, ...props }: SwitchProps) {
  const reactId = useId();
  const sid = id ?? reactId;
  return (
    <div className={cn(styles.row, className)}>
      <RadixSwitch.Root id={sid} className={styles.track} {...props}>
        <RadixSwitch.Thumb className={styles.thumb} />
      </RadixSwitch.Root>
      {label != null && (
        <label htmlFor={sid} className={styles.label}>
          {label}
        </label>
      )}
    </div>
  );
}
