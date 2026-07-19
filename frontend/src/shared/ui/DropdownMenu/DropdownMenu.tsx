import * as RadixDropdown from "@radix-ui/react-dropdown-menu";
import type { ComponentPropsWithoutRef, ReactNode } from "react";
import { cn } from "../_internal/cn";
import styles from "./DropdownMenu.module.css";

export const DropdownMenu = RadixDropdown.Root;
export const DropdownMenuTrigger = RadixDropdown.Trigger;

export function DropdownMenuContent({
  className,
  children,
  align = "end",
  sideOffset = 6,
  ...props
}: ComponentPropsWithoutRef<typeof RadixDropdown.Content>) {
  return (
    <RadixDropdown.Portal>
      <RadixDropdown.Content
        className={cn(styles.content, className)}
        align={align}
        sideOffset={sideOffset}
        {...props}
      >
        {children}
      </RadixDropdown.Content>
    </RadixDropdown.Portal>
  );
}

export interface DropdownMenuItemProps
  extends ComponentPropsWithoutRef<typeof RadixDropdown.Item> {
  icon?: ReactNode;
  tone?: "default" | "danger";
}

export function DropdownMenuItem({
  className,
  icon,
  tone = "default",
  children,
  ...props
}: DropdownMenuItemProps) {
  return (
    <RadixDropdown.Item className={cn(styles.item, styles[tone], className)} {...props}>
      {icon != null && (
        <span className={styles.itemIcon} aria-hidden="true">
          {icon}
        </span>
      )}
      {children}
    </RadixDropdown.Item>
  );
}

export function DropdownMenuLabel({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof RadixDropdown.Label>) {
  return <RadixDropdown.Label className={cn(styles.label, className)} {...props} />;
}

export function DropdownMenuSeparator({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof RadixDropdown.Separator>) {
  return <RadixDropdown.Separator className={cn(styles.separator, className)} {...props} />;
}
