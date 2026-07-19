import * as RadixAvatar from "@radix-ui/react-avatar";
import { cn } from "../_internal/cn";
import styles from "./Avatar.module.css";

export interface AvatarProps {
  src?: string;
  /** Person/company name — drives the alt text and the initials fallback. */
  name: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0]?.toUpperCase() ?? "").join("");
}

export function Avatar({ src, name, size = "md", className }: AvatarProps) {
  return (
    <RadixAvatar.Root className={cn(styles.root, styles[size], className)}>
      {src && <RadixAvatar.Image className={styles.image} src={src} alt={name} />}
      <RadixAvatar.Fallback className={styles.fallback} delayMs={src ? 400 : 0}>
        {initials(name)}
      </RadixAvatar.Fallback>
    </RadixAvatar.Root>
  );
}
