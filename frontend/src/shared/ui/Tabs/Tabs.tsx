import * as RadixTabs from "@radix-ui/react-tabs";
import { useCallback, useEffect, useRef, type ComponentPropsWithoutRef } from "react";
import { cn } from "../_internal/cn";
import styles from "./Tabs.module.css";

export const Tabs = RadixTabs.Root;

export function TabsList({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof RadixTabs.List>) {
  const ref = useRef<HTMLDivElement>(null);

  // The trailing fade says "there is more this way", so it has to go once there
  // isn't. Cheap enough to run on scroll; no observer needed.
  const syncEdge = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.dataset.atEnd = String(el.scrollLeft + el.clientWidth >= el.scrollWidth - 1);
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    syncEdge();
    // an active tab scrolled out of view is invisible until you think to look
    el.querySelector<HTMLElement>('[data-state="active"]')?.scrollIntoView({
      block: "nearest",
      inline: "nearest",
    });
    el.addEventListener("scroll", syncEdge, { passive: true });
    window.addEventListener("resize", syncEdge);
    return () => {
      el.removeEventListener("scroll", syncEdge);
      window.removeEventListener("resize", syncEdge);
    };
  }, [syncEdge]);

  return <RadixTabs.List ref={ref} className={cn(styles.list, className)} {...props} />;
}

export function TabsTrigger({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof RadixTabs.Trigger>) {
  return <RadixTabs.Trigger className={cn(styles.trigger, className)} {...props} />;
}

export function TabsContent({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof RadixTabs.Content>) {
  return <RadixTabs.Content className={cn(styles.content, className)} {...props} />;
}
