// Unified calendar (§2): custom month grid over GET /calendar — the union of
// dated items from every module the user can READ. Each module carries its own
// colour-key so a busy month still shows where the work sits.

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { api } from "../../shared/api";
import type { CalendarEvent } from "../../shared/types";
import { Button, Card, CardHeader } from "../../shared/ui";
import styles from "./CalendarView.module.css";

const DOW = [
  { label: "Mon", full: "Monday" },
  { label: "Tue", full: "Tuesday" },
  { label: "Wed", full: "Wednesday" },
  { label: "Thu", full: "Thursday" },
  { label: "Fri", full: "Friday" },
  { label: "Sat", full: "Saturday" },
  { label: "Sun", full: "Sunday" },
];

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
  // 42 days → six rows of seven, so the table has real weeks
  const weeks = useMemo(
    () => Array.from({ length: 6 }, (_, w) => days.slice(w * 7, w * 7 + 7)),
    [days],
  );

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

      {/* A real table: the month is tabular, display-only data, so a screen
          reader navigates it natively — no ARIA grid contract to honour. */}
      <table className={styles.grid}>
        <caption className={styles.srOnly}>{monthLabel}</caption>
        <thead>
          <tr>
            {DOW.map((d) => (
              <th key={d.label} scope="col" className={styles.dow}>
                <abbr title={d.full}>{d.label}</abbr>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {weeks.map((week) => (
            <tr key={ymd(week[0])}>
              {week.map((d) => {
                const key = ymd(d);
                const dayEvents = byDay.get(key) ?? [];
                const dim = d.getMonth() !== anchor.getMonth();
                const isToday = key === today;
                return (
                  <td
                    key={key}
                    className={[
                      styles.cell,
                      dim ? styles.dim : "",
                      isToday ? styles.today : "",
                    ].filter(Boolean).join(" ")}
                    aria-current={isToday ? "date" : undefined}
                  >
                    {/* the visible number lacks month/year context on its own;
                        the full date is what a screen reader should hear */}
                    <span className={styles.srOnly}>
                      {d.toLocaleDateString(undefined, {
                        weekday: "long", month: "long", day: "numeric",
                      })}
                      {dayEvents.length > 0 &&
                        `, ${dayEvents.length} event${dayEvents.length === 1 ? "" : "s"}`}
                    </span>
                    <span className={styles.dayNum} aria-hidden="true">{d.getDate()}</span>
                    {dayEvents.slice(0, 3).map((e) => (
                      <span key={e.id} className={styles.chip} style={accent(e.color_key)} title={e.title}>
                        {e.title}
                      </span>
                    ))}
                    {dayEvents.length > 3 && (
                      <span className={styles.more}>+{dayEvents.length - 3} more</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

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
