import * as RadixRadio from "@radix-ui/react-radio-group";
import { useId, type ComponentPropsWithoutRef, type ReactNode } from "react";
import { cn } from "../_internal/cn";
import styles from "./Radio.module.css";

export type RadioGroupProps = ComponentPropsWithoutRef<typeof RadixRadio.Root>;

export function RadioGroup({ className, ...props }: RadioGroupProps) {
  return <RadixRadio.Root className={cn(styles.group, className)} {...props} />;
}

export interface RadioProps {
  value: string;
  label?: ReactNode;
  disabled?: boolean;
  id?: string;
  className?: string;
}

export function Radio({ value, label, disabled, id, className }: RadioProps) {
  const reactId = useId();
  const rid = id ?? reactId;
  return (
    <div className={cn(styles.row, className)}>
      <RadixRadio.Item id={rid} value={value} disabled={disabled} className={styles.item}>
        <RadixRadio.Indicator className={styles.indicator} />
      </RadixRadio.Item>
      {label != null && (
        <label htmlFor={rid} className={styles.label}>
          {label}
        </label>
      )}
    </div>
  );
}
