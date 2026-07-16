// Unified calendar (§2): custom month grid over GET /calendar — the union of
// dated items from every module the user can READ.

import { useEffect, useMemo, useState } from "react";
import { api } from "../../shared/api";
import type { CalendarEvent } from "../../shared/types";
import { Button, Card } from "../../shared/ui";

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
  const title = anchor.toLocaleDateString(undefined, {
    month: "long", year: "numeric",
  });

  return (
    <Card
      title="Calendar"
      actions={
        <div className="cal-toolbar">
          <Button variant="ghost" onClick={() =>
            setAnchor(new Date(anchor.getFullYear(), anchor.getMonth() - 1, 1))}>
            ←
          </Button>
          <span className="cal-title">{title}</span>
          <Button variant="ghost" onClick={() =>
            setAnchor(new Date(anchor.getFullYear(), anchor.getMonth() + 1, 1))}>
            →
          </Button>
        </div>
      }
    >
      <div className="cal-grid">
        {DOW.map((d) => (
          <div key={d} className="cal-dow">{d}</div>
        ))}
        {days.map((d) => {
          const key = ymd(d);
          const dayEvents = byDay.get(key) ?? [];
          const dim = d.getMonth() !== anchor.getMonth();
          return (
            <div key={key}
              className={`cal-cell ${dim ? "dim" : ""} ${key === today ? "today" : ""}`}>
              <span className="day-num">{d.getDate()}</span>
              {dayEvents.slice(0, 3).map((e) => (
                <span key={e.id} className={`cal-chip mod-${e.color_key}`} title={e.title}>
                  {e.title}
                </span>
              ))}
              {dayEvents.length > 3 && (
                <span className="cal-more">+{dayEvents.length - 3} more</span>
              )}
            </div>
          );
        })}
      </div>
      {modulesInView.length > 0 && (
        <div className="cal-legend">
          {modulesInView.map((m) => (
            <span key={m}>
              <i className={`legend-dot mod-${m}`} /> {m}
            </span>
          ))}
        </div>
      )}
    </Card>
  );
}
