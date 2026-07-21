// Unified calendar (§2): custom month grid over GET /calendar — the union of
// dated items from every module the user can READ. Each module carries its own
// colour-key so a busy month still shows where the work sits.

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { api } from "../../shared/api";
import type { CalendarEvent } from "../../shared/types";
import { Button, Card, CardHeader } from "../../shared/ui";
import styles from "./CalendarView.module.css";

const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function monthGrid(anchor: Date): Date[] {
  const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
  const start = new Date(first);
  start.setDate(first.getDate() - ((first.getDay() + 6) % 7)); // back to Monday
  return Array.from({ length: 42 }, (_, i) => {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    return d;
  });
}

/** A module's colour-key resolves to a design-system accent, never a raw hex. */
function accent(colorKey: string): CSSProperties {
  return { "--chip-accent": `var(--accent-${colorKey}, var(--n-400))` } as CSSProperties;
}

export function CalendarView() {
  const [anchor, setAnchor] = useState(() => new Date());
  const [events, setEvents] = useState<CalendarEvent[]>([]);

  const days = useMemo(() => monthGrid(anchor), [anchor]);

  useEffect(() => {
    const from = ymd(days[0]);
    const to = ymd(days[days.length - 1]);
    api<CalendarEvent[]>(`/calendar?from=${from}&to=${to}`)
      .then((res) => setEvents(res.data))
      .catch(() => setEvents([]));
  }, [days]);

  const byDay = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>();
    for (const e of events) {
      const key = e.start.slice(0, 10);
      map.set(key, [...(map.get(key) ?? []), e]);
    }
    return map;
  }, [events]);

  const today = ymd(new Date());
  const modulesInView = [...new Set(events.map((e) => e.color_key))];
  const monthLabel = anchor.toLocaleDateString(undefined, { month: "long", year: "numeric" });

  function shift(months: number) {
    setAnchor(new Date(anchor.getFullYear(), anchor.getMonth() + months, 1));
  }

  return (
    <Card>
      <CardHeader
        title="Calendar"
        description={`${events.length} scheduled item${events.length === 1 ? "" : "s"} this view`}
        actions={
          <div className={styles.toolbar}>
            <Button variant="ghost" size="compact" onClick={() => shift(-1)}
              aria-label="Previous month">
              <ChevronLeft size={16} />
            </Button>
            <span className={styles.monthLabel}>{monthLabel}</span>
            <Button variant="ghost" size="compact" onClick={() => shift(1)}
              aria-label="Next month">
              <ChevronRight size={16} />
            </Button>
          </div>
        }
      />

      <div className={styles.grid}>
        {DOW.map((d) => (
          <div key={d} className={styles.dow}>{d}</div>
        ))}
        {days.map((d) => {
          const key = ymd(d);
          const dayEvents = byDay.get(key) ?? [];
          const dim = d.getMonth() !== anchor.getMonth();
          return (
            <div
              key={key}
              className={[
                styles.cell,
                dim ? styles.dim : "",
                key === today ? styles.today : "",
              ].filter(Boolean).join(" ")}
            >
              <span className={styles.dayNum}>{d.getDate()}</span>
              {dayEvents.slice(0, 3).map((e) => (
                <span key={e.id} className={styles.chip} style={accent(e.color_key)} title={e.title}>
                  {e.title}
                </span>
              ))}
              {dayEvents.length > 3 && (
                <span className={styles.more}>+{dayEvents.length - 3} more</span>
              )}
            </div>
          );
        })}
      </div>

      {modulesInView.length > 0 && (
        <div className={styles.legend}>
          {modulesInView.map((m) => (
            <span key={m} className={styles.legendItem}>
              <i className={styles.legendDot} style={accent(m)} aria-hidden="true" />
              {m}
            </span>
          ))}
        </div>
      )}
    </Card>
  );
}
