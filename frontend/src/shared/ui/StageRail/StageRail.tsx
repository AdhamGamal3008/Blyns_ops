import { Check, TriangleAlert, X } from "lucide-react";
import { useEffect, useRef } from "react";
import { cn } from "../_internal/cn";
import styles from "./StageRail.module.css";

export type StageState =
  | "pending"
  | "waiting"
  | "blocked"
  | "in_progress"
  | "validation"
  | "pending_approval"
  | "approved"
  | "rejected"
  | "on_hold";

export interface RailStage {
  order: number;
  key: string;
  name: string;
  status: StageState;
  approverRole?: string | null;
  blockingReason?: string | null;
}

export interface StageRailProps {
  stages: RailStage[];
  currentOrder: number;
  selectedKey?: string;
  onSelect?: (stage: RailStage) => void;
  /** "auto" = horizontal rail on desktop, vertical timeline on mobile. */
  orientation?: "auto" | "horizontal" | "vertical";
  className?: string;
}

type Visual = "done" | "gate" | "active" | "warn" | "alert" | "upcoming";

/** Gold marks the live gate; oxblood is reserved for a rejected/held stage. */
function visualFor(status: StageState, order: number, currentOrder: number): Visual {
  if (status === "approved") return "done";
  if (status === "rejected" || status === "on_hold") return "alert";
  if (status === "blocked" || status === "waiting") return "warn";
  if (status === "pending_approval" || status === "validation") return "gate";
  if (status === "in_progress") return "active";
  return order < currentOrder ? "done" : "upcoming";
}

const STATUS_LABEL: Record<StageState, string> = {
  pending: "Not started",
  waiting: "Waiting",
  blocked: "Blocked",
  in_progress: "In progress",
  validation: "Validating",
  pending_approval: "Awaiting approval",
  approved: "Approved",
  rejected: "Rejected",
  on_hold: "On hold",
};

export function StageRail({
  stages,
  currentOrder,
  selectedKey,
  onSelect,
  orientation = "auto",
  className,
}: StageRailProps) {
  const currentRef = useRef<HTMLLIElement>(null);

  useEffect(() => {
    const node = currentRef.current;
    // scrollIntoView is absent under jsdom and some SSR shims; it is a nicety
    // (centre the live gate), never load-bearing, so skip it when missing
    if (!node || typeof node.scrollIntoView !== "function") return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    node.scrollIntoView({
      behavior: reduce ? "auto" : "smooth",
      inline: "center",
      block: "nearest",
    });
  }, [currentOrder]);

  return (
    <ol className={cn(styles.rail, styles[orientation], className)} aria-label="Project stages">
      {stages.map((stage) => {
        const visual = visualFor(stage.status, stage.order, currentOrder);
        const isCurrent = stage.order === currentOrder;
        const isSelected = selectedKey ? stage.key === selectedKey : isCurrent;
        const reached = stage.order < currentOrder;
        const interactive = Boolean(onSelect);

        const marker =
          visual === "done" ? (
            <Check size={14} strokeWidth={3} />
          ) : visual === "alert" ? (
            <X size={14} strokeWidth={3} />
          ) : visual === "warn" ? (
            <TriangleAlert size={13} strokeWidth={2.5} />
          ) : (
            stage.order
          );

        const content = (
          <>
            <span className={styles.marker}>
              <span className={styles.dot}>{marker}</span>
              <span className={cn(styles.connector, reached && styles.connectorReached)} />
            </span>
            <span className={styles.body}>
              <span className={styles.name}>{stage.name}</span>
              <span className={styles.meta}>{STATUS_LABEL[stage.status]}</span>
              {stage.blockingReason && (
                <span className={styles.blocking}>{stage.blockingReason}</span>
              )}
            </span>
          </>
        );

        return (
          <li
            key={stage.key}
            ref={isCurrent ? currentRef : undefined}
            className={cn(
              styles.stage,
              styles[visual],
              isCurrent && styles.current,
              isSelected && styles.selected,
            )}
            aria-current={isCurrent ? "step" : undefined}
          >
            {interactive ? (
              <button
                type="button"
                className={styles.hit}
                onClick={() => onSelect?.(stage)}
                // an aria-label overrides the inner text, so the blocking reason
                // (visible in the body) has to be folded in or it goes unheard
                aria-label={
                  `Stage ${stage.order}: ${stage.name} — ${STATUS_LABEL[stage.status]}` +
                  (stage.blockingReason ? `. ${stage.blockingReason}` : "")
                }
              >
                {content}
              </button>
            ) : (
              <div className={styles.hit}>{content}</div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
