// System Activity Panel (§3): short-polling feed (15s) from activity_log,
// filtered server-side to READ-permitted modules.

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../shared/api";
import type { ActivityEntry, ClientMe } from "../../shared/types";
import { Button, Card, timeAgo } from "../../shared/legacy-ui";

const POLL_MS = 15_000;

export function ActivityPanel(props: { me: ClientMe }) {
  const [entries, setEntries] = useState<ActivityEntry[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [moduleFilter, setModuleFilter] = useState("");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const readableModules = Object.entries(props.me.role.permissions)
    .filter(([k, v]) => v >= 2 && props.me.company.enabled_modules.includes(k))
    .map(([k]) => k);

  const load = useCallback(async () => {
    const q = moduleFilter ? `&module=${moduleFilter}` : "";
    try {
      const res = await api<ActivityEntry[]>(`/activity?page_size=20${q}`);
      setEntries(res.data);
      setCursor((res.meta?.next_cursor as string | null) ?? null);
    } catch {
      // keep last known entries
    }
  }, [moduleFilter]);

  useEffect(() => {
    load();
    timer.current = setInterval(load, POLL_MS);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [load]);

  async function loadMore() {
    if (!cursor) return;
    const q = moduleFilter ? `&module=${moduleFilter}` : "";
    const res = await api<ActivityEntry[]>(
      `/activity?page_size=20&cursor=${cursor}${q}`,
    );
    setEntries((prev) => [...prev, ...res.data]);
    setCursor((res.meta?.next_cursor as string | null) ?? null);
  }

  return (
    <Card
      title="Activity"
      actions={
        <select value={moduleFilter} style={{ width: 130 }}
          onChange={(e) => setModuleFilter(e.target.value)}>
          <option value="">All modules</option>
          {readableModules.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      }
    >
      <div className="feed">
        {entries.length === 0 && <p className="muted">No activity yet.</p>}
        {entries.map((e) => (
          <div key={e.id} className="feed-item">
            <span className={`feed-dot mod-${e.module ?? "dashboard"}`} />
            <div className="feed-body">
              <div className="feed-line">
                <b>{e.actor_name ?? e.actor_id}</b> · {e.action}
                {e.entity?.label ? <> — {e.entity.label}</> : null}
              </div>
              <div className="feed-meta">
                {e.module ?? "system"} · {timeAgo(e.occurred_at)}
              </div>
            </div>
          </div>
        ))}
      </div>
      {cursor && (
        <div style={{ marginTop: 10 }}>
          <Button variant="ghost" onClick={loadMore}>Load more</Button>
        </div>
      )}
    </Card>
  );
}
