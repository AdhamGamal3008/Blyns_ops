// A surface anchored to a trigger, for detail a tooltip is too small to hold.
//
// Tooltip is for a short string and is hover/focus only; this one holds real
// content — headings, rows, links — so it is click-activated by default and its
// content is focusable. `open`/`onOpenChange` are exposed so a caller can add
// its own opening rules (the calendar previews on hover and pins on click)
// without reimplementing the positioning.

import * as RadixPopover from "@radix-ui/react-popover";
import type { ComponentPropsWithoutRef, ReactNode } from "react";
import { cn } from "../_internal/cn";
import styles from "./Popover.module.css";

export interface PopoverProps {
  trigger: ReactNode;
  children: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  side?: "top" | "right" | "bottom" | "left";
  align?: "start" | "center" | "end";
  /** Wider surface for list content. */
  size?: "md" | "lg";
  /** Keep focus on the trigger when opening — for hover-previews, where
   *  yanking focus into the panel would fight the pointer. */
  keepFocus?: boolean;
  className?: string;
  contentProps?: ComponentPropsWithoutRef<typeof RadixPopover.Content>;
}

export function Popover({
  trigger,
  children,
  open,
  onOpenChange,
  side = "top",
  align = "center",
  size = "md",
  keepFocus,
  className,
  contentProps,
}: PopoverProps) {
  return (
    <RadixPopover.Root open={open} onOpenChange={onOpenChange}>
      <RadixPopover.Trigger asChild>{trigger}</RadixPopover.Trigger>
      <RadixPopover.Portal>
        <RadixPopover.Content
          className={cn(styles.content, styles[size], className)}
          side={side}
          align={align}
          sideOffset={6}
          collisionPadding={8}
          onOpenAutoFocus={keepFocus ? (e) => e.preventDefault() : undefined}
          {...contentProps}
        >
          {children}
          <RadixPopover.Arrow className={styles.arrow} />
        </RadixPopover.Content>
      </RadixPopover.Portal>
    </RadixPopover.Root>
  );
}
