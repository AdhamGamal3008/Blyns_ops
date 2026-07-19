import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "../_internal/cn";
import styles from "./Pagination.module.css";

export interface PaginationProps {
  page: number;
  pageCount: number;
  onPageChange: (page: number) => void;
  siblingCount?: number;
  className?: string;
}

function range(start: number, end: number): number[] {
  const out: number[] = [];
  for (let i = start; i <= end; i++) out.push(i);
  return out;
}

/** Page items with "dots" ellipsis markers, keeping first/last always visible. */
function paginationItems(current: number, total: number, siblings: number): (number | "dots")[] {
  const totalNumbers = siblings * 2 + 5;
  if (total <= totalNumbers) return range(1, total);

  const leftSibling = Math.max(current - siblings, 1);
  const rightSibling = Math.min(current + siblings, total);
  const showLeftDots = leftSibling > 3;
  const showRightDots = rightSibling < total - 2;

  if (!showLeftDots && showRightDots) {
    return [...range(1, 3 + 2 * siblings), "dots", total];
  }
  if (showLeftDots && !showRightDots) {
    return [1, "dots", ...range(total - (2 + 2 * siblings), total)];
  }
  return [1, "dots", ...range(leftSibling, rightSibling), "dots", total];
}

export function Pagination({
  page,
  pageCount,
  onPageChange,
  siblingCount = 1,
  className,
}: PaginationProps) {
  if (pageCount <= 1) return null;
  const items = paginationItems(page, pageCount, siblingCount);

  return (
    <nav className={cn(styles.root, className)} aria-label="Pagination">
      <button
        type="button"
        className={styles.page}
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1}
        aria-label="Previous page"
      >
        <ChevronLeft size={16} />
      </button>

      {items.map((item, i) =>
        item === "dots" ? (
          <span key={`dots-${i}`} className={styles.dots} aria-hidden="true">
            …
          </span>
        ) : (
          <button
            key={item}
            type="button"
            className={cn(styles.page, item === page && styles.active)}
            onClick={() => onPageChange(item)}
            aria-current={item === page ? "page" : undefined}
          >
            {item}
          </button>
        ),
      )}

      <button
        type="button"
        className={styles.page}
        onClick={() => onPageChange(page + 1)}
        disabled={page >= pageCount}
        aria-label="Next page"
      >
        <ChevronRight size={16} />
      </button>
    </nav>
  );
}
