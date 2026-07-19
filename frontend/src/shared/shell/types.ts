import type { ReactNode } from "react";

export interface ShellNavItem {
  key: string;
  label: string;
  to: string;
  icon: ReactNode;
  /** Match the route exactly (for index routes like the dashboard). */
  end?: boolean;
}

export interface ShellUser {
  name: string;
  role: string;
}

export interface CommandItem {
  id: string;
  label: string;
  hint?: string;
  icon?: ReactNode;
  group?: string;
  keywords?: string;
  onSelect: () => void;
}
