// Quick view for a calendar entry (docs/modules/CLIENT_DASHBOARD.md §2).
//
// Opens two ways, deliberately. Hovering previews it, which is what a pointer
// user reaches for; clicking (or Enter/Space) pins it open, which is the only
// path a keyboard or a touchscreen has — a hover-only detail is unreachable for
// both. Pinned is also the state where the panel can be read at leisure and its
// "Open in …" link followed, so the pointer leaving must not close it.

import { ArrowUpRight } from "lucide-react";
import { useRef, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import type { CalendarEvent } from "../../shared/types";
import { Badge, Popover } from "../../shared/ui";
import styles from "./EventPopover.module.css";

const HOVER_OPEN_MS = 140;
const HOVER_CLOSE_MS = 120;

/** Human labels for the normalized `type` values the API emits (§2). */
const TYPE_LABEL: Record<string, string> = {
  milestone: "Milestone",
  stage_due: "Stage target",
  delivery: "Delivery",
  acclimation: "Acclimation window",
  gate_due: "Gate deadline",
  deal_close: "Expected close",
  task_due: "Task due",
  invoice_due: "Invoice due",
  bill_due: "Bill due",
  company_event: "Company event",
};

export function typeLabel(type: string): string {
  return TYPE_LABEL[type] ?? type.replace(/_/g, " ");
}

/** Where an event's source entity lives in the SPA. Only projects have a
 *  per-record route today, so everything else lands on its module's page —
 *  still the spec's "deep-link to its source entity", at the granularity the
 *  router actually offers. */
export function deepLink(event: CalendarEvent): string {
  const { module, type, id } = event.entity_ref;
  if (module === "projects" && type === "project") return `/app/projects/${id}`;
  if (module === "settings") return "/app/settings";
  return `/app/${module}`;
}

function formatWhen(event: CalendarEvent): string {
  const start = new Date(event.start);
  const dayOpts: Intl.DateTimeFormatOptions = {
    weekday: "short", day: "numeric", month: "short", year: "numeric",
  };
  const day = start.toLocaleDateString(undefined, dayOpts);
  const end = event.end ? new Date(event.end) : null;

  if (event.all_day) {
    // A window (acclimation, a multi-day company event) reads as a range.
    if (end && end.toDateString() !== start.toDateString()) {
      return `${day} → ${end.toLocaleDateString(undefined, dayOpts)}`;
    }
    return `${day} · all day`;
  }
  const time = start.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  return `${day} · ${time}`;
}

function money(value: number, currency?: string): string {
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency", currency: currency || "USD", maximumFractionDigits: 0,
    }).format(value);
  } catch {
    return `${value}`;
  }
}

/** Meta → display rows, per event type. Unknown keys are ignored rather than
 *  dumped, so the server can enrich `meta` without the UI showing raw field
 *  names to a user. */
function detailRows(event: CalendarEvent): { label: string; value: string }[] {
  const m = event.meta ?? {};
  const rows: { label: string; value: string }[] = [];
  const str = (k: string) => (typeof m[k] === "string" ? (m[k] as string) : null);
  const num = (k: string) => (typeof m[k] === "number" ? (m[k] as number) : null);

  switch (event.type) {
    case "deal_close": {
      const amount = num("amount");
      if (amount != null) rows.push({ label: "Value", value: money(amount, str("currency") ?? undefined) });
      const stage = str("stage");
      if (stage) rows.push({ label: "Stage", value: stage });
      const pct = num("probability_pct");
      if (pct != null) rows.push({ label: "Probability", value: `${pct}%` });
      break;
    }
    case "task_due": {
      const kind = str("activity_type");
      if (kind) rows.push({ label: "Type", value: kind });
      const about = str("about");
      if (about) rows.push({ label: "About", value: about });
      const notes = str("notes");
      if (notes) rows.push({ label: "Notes", value: notes });
      break;
    }
    case "invoice_due":
    case "bill_due": {
      const who = str("counterparty");
      if (who) rows.push({ label: event.type === "bill_due" ? "Vendor" : "Customer", value: who });
      const balance = num("balance");
      const currency = str("currency") ?? undefined;
      if (balance != null) rows.push({ label: "Outstanding", value: money(balance, currency) });
      const total = num("total");
      // Only worth showing the face value when part of it is already paid.
      if (total != null && balance != null && total !== balance) {
        rows.push({ label: "Invoice total", value: money(total, currency) });
      }
      const status = str("status");
      if (status) rows.push({ label: "Status", value: status.replace(/_/g, " ") });
      break;
    }
    case "company_event": {
      const visibility = str("visibility");
      if (visibility) rows.push({ label: "Visible to", value: visibility });
      break;
    }
    default: {
      // every projects event
      const code = str("code");
      if (code) rows.push({ label: "Project", value: code });
      const stage = str("stage") ?? str("gate") ?? str("milestone");
      if (stage) rows.push({ label: "Item", value: stage.replace(/_/g, " ") });
      const order = num("stage_order");
      if (order != null) rows.push({ label: "Now at stage", value: String(order) });
      const status = str("status");
      if (status) rows.push({ label: "Status", value: status });
    }
  }
  return rows;
}

function accent(colorKey: string): CSSProperties {
  return { "--chip-accent": `var(--accent-${colorKey}, var(--n-400))` } as CSSProperties;
}

export function EventDetail(props: { event: CalendarEvent; onNavigate?: () => void }) {
  const { event } = props;
  const rows = detailRows(event);
  return (
    <div className={styles.detail}>
      <p className={styles.detailTitle}>{event.title}</p>
      <div className={styles.badges}>
        <Badge tone="neutral">{typeLabel(event.type)}</Badge>
        <Badge tone="neutral">
          <span className={styles.moduleName}>{event.source_module}</span>
        </Badge>
      </div>
      <p className={styles.when}>{formatWhen(event)}</p>

      {rows.length > 0 && (
        <dl className={styles.rows}>
          {rows.map((r) => (
            <div key={r.label} className={styles.row}>
              <dt>{r.label}</dt>
              <dd>{r.value}</dd>
            </div>
          ))}
        </dl>
      )}

      <Link to={deepLink(event)} className={styles.open} onClick={props.onNavigate}>
        Open in <span className={styles.moduleName}>{event.source_module}</span>
        <ArrowUpRight size={14} aria-hidden="true" />
      </Link>
    </div>
  );
}

/** Hover-preview / click-to-pin machinery shared by both triggers.
 *
 * "Pinned" is the whole point of the distinction: a hovered panel must vanish
 * when the pointer leaves, but a clicked one has to survive that — otherwise
 * moving the mouse toward its "Open in …" link would dismiss it before you
 * arrived. Pinning is also what tells the panel to take focus, so a keyboard
 * user lands inside it rather than behind it.
 */
function useHoverPin() {
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  // Timer callbacks outlive the render that scheduled them, so they read the
  // ref; `pinned` state exists only to drive `keepFocus` at render time.
  const pinnedRef = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clear = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };

  const pin = (next: boolean) => {
    pinnedRef.current = next;
    setPinned(next);
  };

  return {
    open,
    pinned,
    /** Radix drives this for click, Escape and outside-click. */
    onOpenChange: (next: boolean) => {
      clear();
      pin(next);
      setOpen(next);
    },
    triggerProps: {
      onMouseEnter: () => {
        clear();
        timer.current = setTimeout(() => setOpen(true), HOVER_OPEN_MS);
      },
      onMouseLeave: () => {
        clear();
        if (!pinnedRef.current) {
          timer.current = setTimeout(() => setOpen(false), HOVER_CLOSE_MS);
        }
      },
      onClick: (e: React.MouseEvent) => {
        if (open && !pinnedRef.current) {
          // Hover already opened it, so Radix's trigger would read this click
          // as "toggle shut". Pin it instead — preventDefault stops Radix's own
          // handler, which composeEventHandlers skips once default is prevented.
          e.preventDefault();
          pin(true);
        }
      },
    },
    /** Keep the panel alive while the pointer is inside it. */
    contentHoverProps: {
      onMouseEnter: () => clear(),
      onMouseLeave: () => {
        if (!pinnedRef.current) setOpen(false);
      },
    },
    unpin: () => {
      pin(false);
      setOpen(false);
    },
  };
}

export function EventChip(props: { event: CalendarEvent }) {
  const { event } = props;
  const { open, pinned, onOpenChange, triggerProps, contentHoverProps, unpin } =
    useHoverPin();

  return (
    <Popover
      open={open}
      onOpenChange={onOpenChange}
      side="top"
      align="start"
      keepFocus={!pinned}
      contentProps={contentHoverProps}
      trigger={
        <button
          type="button"
          className={styles.chip}
          style={accent(event.color_key)}
          data-testid="calendar-chip"
          {...triggerProps}
        >
          <span className={styles.chipText}>{event.title}</span>
          <span className={styles.srOnly}>
            {" "}— {typeLabel(event.type)}, {formatWhen(event)}
          </span>
        </button>
      }
    >
      <EventDetail event={event} onNavigate={unpin} />
    </Popover>
  );
}

/** "+N more" → the whole day, since the cell can only show the first few. */
export function DayOverflow(props: { date: Date; events: CalendarEvent[]; hidden: number }) {
  const { open, pinned, onOpenChange, triggerProps, contentHoverProps, unpin } =
    useHoverPin();
  const dayLabel = props.date.toLocaleDateString(undefined, {
    weekday: "long", day: "numeric", month: "long",
  });

  return (
    <Popover
      open={open}
      onOpenChange={onOpenChange}
      side="top"
      align="start"
      size="lg"
      keepFocus={!pinned}
      contentProps={contentHoverProps}
      trigger={
        <button
          type="button"
          className={styles.more}
          data-testid="calendar-more"
          {...triggerProps}
        >
          +{props.hidden} more
        </button>
      }
    >
      <div className={styles.detail}>
        <p className={styles.detailTitle}>{dayLabel}</p>
        <p className={styles.when}>
          {props.events.length} scheduled item{props.events.length === 1 ? "" : "s"}
        </p>
        <ul className={styles.dayList}>
          {props.events.map((e) => (
            <li key={e.id}>
              <Link to={deepLink(e)} className={styles.dayItem} onClick={unpin}>
                <i className={styles.dot} style={accent(e.color_key)} aria-hidden="true" />
                <span className={styles.dayItemTitle}>{e.title}</span>
                <span className={styles.dayItemType}>{typeLabel(e.type)}</span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </Popover>
  );
}
