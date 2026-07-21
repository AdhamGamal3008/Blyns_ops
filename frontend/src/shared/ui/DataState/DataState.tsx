import type { ReactNode } from "react";
import { EmptyState } from "../EmptyState/EmptyState";
import { ErrorState } from "../ErrorState/ErrorState";
import { Skeleton } from "../Skeleton/Skeleton";

export interface DataStateProps {
  loading?: boolean;
  error?: unknown;
  isEmpty?: boolean;
  /** Custom loading placeholder (defaults to skeleton rows). */
  skeleton?: ReactNode;
  /** Custom empty state (defaults to a generic EmptyState). */
  empty?: ReactNode;
  emptyTitle?: ReactNode;
  emptyDescription?: ReactNode;
  onRetry?: () => void;
  children: ReactNode;
}

function errorMessage(error: unknown): string | undefined {
  if (!error) return undefined;
  if (error instanceof Error) return error.message;
  return String(error);
}

function DefaultSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}>
      {Array.from({ length: 4 }).map((_, i) => (
        <Skeleton key={i} height={44} />
      ))}
    </div>
  );
}

/**
 * Switches an async surface between error / loading / empty / data, so every
 * data view ships all four states by construction.
 */
export function DataState({
  loading,
  error,
  isEmpty,
  skeleton,
  empty,
  emptyTitle = "Nothing here yet",
  emptyDescription,
  onRetry,
  children,
}: DataStateProps) {
  if (error) {
    return <ErrorState description={errorMessage(error)} onRetry={onRetry} />;
  }
  if (loading) {
    return <>{skeleton ?? <DefaultSkeleton />}</>;
  }
  if (isEmpty) {
    return <>{empty ?? <EmptyState title={emptyTitle} description={emptyDescription} />}</>;
  }
  return <>{children}</>;
}
