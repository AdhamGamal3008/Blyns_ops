import * as RadixToast from "@radix-ui/react-toast";
import {
  CircleAlert,
  CircleCheck,
  Info,
  TriangleAlert,
  X,
  type LucideIcon,
} from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { cn } from "../_internal/cn";
import styles from "./Toast.module.css";

export type ToastTone = "info" | "success" | "warning" | "danger";

export interface ToastOptions {
  title: ReactNode;
  description?: ReactNode;
  tone?: ToastTone;
  duration?: number;
}

interface ToastItem extends ToastOptions {
  id: number;
}

const icons: Record<ToastTone, LucideIcon> = {
  info: Info,
  success: CircleCheck,
  warning: TriangleAlert,
  danger: CircleAlert,
};

interface ToastContextValue {
  toast: (options: ToastOptions) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let counter = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const toast = useCallback((options: ToastOptions) => {
    setItems((prev) => [...prev, { ...options, id: ++counter }]);
  }, []);
  const remove = useCallback((id: number) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);
  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      <RadixToast.Provider swipeDirection="right" duration={5000}>
        {children}
        {items.map((item) => {
          const tone = item.tone ?? "info";
          const Icon = icons[tone];
          return (
            <RadixToast.Root
              key={item.id}
              className={cn(styles.toast, styles[tone])}
              duration={item.duration}
              onOpenChange={(open) => {
                if (!open) remove(item.id);
              }}
            >
              <span className={styles.icon} aria-hidden="true">
                <Icon size={18} />
              </span>
              <div className={styles.body}>
                <RadixToast.Title className={styles.title}>{item.title}</RadixToast.Title>
                {item.description != null && (
                  <RadixToast.Description className={styles.description}>
                    {item.description}
                  </RadixToast.Description>
                )}
              </div>
              <RadixToast.Close className={styles.close} aria-label="Dismiss">
                <X size={16} />
              </RadixToast.Close>
            </RadixToast.Root>
          );
        })}
        <RadixToast.Viewport className={styles.viewport} />
      </RadixToast.Provider>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within a ToastProvider");
  return ctx;
}
