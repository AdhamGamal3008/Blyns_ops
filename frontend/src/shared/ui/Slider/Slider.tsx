import * as RadixSlider from "@radix-ui/react-slider";
import { type ComponentPropsWithoutRef } from "react";
import { cn } from "../_internal/cn";
import styles from "./Slider.module.css";

export type SliderProps = ComponentPropsWithoutRef<typeof RadixSlider.Root>;

export function Slider({ className, ...props }: SliderProps) {
  const source = props.value ?? props.defaultValue ?? [0];
  const thumbCount = Array.isArray(source) ? source.length : 1;
  return (
    <RadixSlider.Root className={cn(styles.root, className)} {...props}>
      <RadixSlider.Track className={styles.track}>
        <RadixSlider.Range className={styles.range} />
      </RadixSlider.Track>
      {Array.from({ length: thumbCount }).map((_, i) => (
        <RadixSlider.Thumb key={i} className={styles.thumb} aria-label={`Value ${i + 1}`} />
      ))}
    </RadixSlider.Root>
  );
}
