import { ChevronRight } from "lucide-react";
import { Fragment } from "react";
import { cn } from "../_internal/cn";
import styles from "./Breadcrumb.module.css";

export interface BreadcrumbItem {
  label: string;
  href?: string;
  onClick?: () => void;
}

export interface BreadcrumbProps {
  items: BreadcrumbItem[];
  className?: string;
}

export function Breadcrumb({ items, className }: BreadcrumbProps) {
  return (
    <nav aria-label="Breadcrumb" className={cn(styles.root, className)}>
      <ol className={styles.list}>
        {items.map((item, i) => {
          const isLast = i === items.length - 1;
          return (
            <Fragment key={i}>
              <li className={styles.item}>
                {isLast || (!item.href && !item.onClick) ? (
                  <span className={styles.current} aria-current={isLast ? "page" : undefined}>
                    {item.label}
                  </span>
                ) : (
                  <a
                    className={styles.link}
                    href={item.href}
                    onClick={
                      item.onClick
                        ? (e) => {
                            if (!item.href) e.preventDefault();
                            item.onClick?.();
                          }
                        : undefined
                    }
                  >
                    {item.label}
                  </a>
                )}
              </li>
              {!isLast && (
                <li className={styles.separator} aria-hidden="true">
                  <ChevronRight size={14} />
                </li>
              )}
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}
