// System Activity Panel (§3): short-polling feed (15s) from activity_log,
// filtered server-side to READ-permitted modules.

import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { api } from "../../shared/api";
import { timeAgo } from "../../shared/legacy-ui";
import type { ActivityEntry, ClientMe } from "../../shared/types";
import { Button, Card, CardHeader, EmptyState, Select } from "../../shared/ui";
import styles from "./ActivityPanel.module.css";

const POLL_MS = 15_000;
const ALL_MODULES = "__all";

export function ActivityPanel(props: { me: ClientMe }) {
  const [entries, setEntries] = useState<ActivityEntry[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [moduleFilter, setModuleFilter] = useState(ALL_MODULES);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const readableModules = Object.entries(props.me.role.permissions)
    .filter(([k, v]) => v >= 2 && props.me.company.enabled_modules.includes(k))
    .map(([k]) => k);

  const load = useCallback(async () => {
    const q = moduleFilter === ALL_MODULES ? "" : `&module=${moduleFilter}`;
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
    const q = moduleFilter === ALL_MODULES ? "" : `&module=${moduleFilter}`;
    const res = await api<ActivityEntry[]>(
      `/activity?page_size=20&cursor=${cursor}${q}`,
    );
    setEntries((prev) => [...prev, ...res.data]);
    setCursor((res.meta?.next_cursor as string | null) ?? null);
  }

  return (
    <Card>
      <CardHeader
        title="Activity"
        actions={
          <Select
            selectSize="compact"
            value={moduleFilter}
            onValueChange={setModuleFilter}
            className={styles.filter}
            options={[
              { value: ALL_MODULES, label: "All modules" },
              ...readableModules.map((m) => ({ value: m, label: m })),
            ]}
          />
        }
      />

      {entries.length === 0 ? (
        <EmptyState
          title="No activity yet"
          description="Every write across the workspace lands here."
        />
      ) : (
        <ol className={styles.feed}>
          {entries.map((e) => (
            <li key={e.id} className={styles.item}>
              <span
                className={styles.dot}
                style={{
                  "--chip-accent": `var(--accent-${e.module ?? "dashboard"}, var(--n-400))`,
                } as CSSProperties}
                aria-hidden="true"
              />
              <div className={styles.body}>
                <p className={styles.line}>
                  <b>{e.actor_name ?? e.actor_id}</b> {e.action}
                  {e.entity?.label ? <> — {e.entity.label}</> : null}
                </p>
                <p className={styles.meta}>
                  {e.module ?? "system"} · {timeAgo(e.occurred_at)}
                </p>
              </div>
            </li>
          ))}
        </ol>
      )}

      {cursor && (
        <div className={styles.more}>
          <Button variant="ghost" size="compact" onClick={loadMore}>Load more</Button>
        </div>
      )}
    </Card>
  );
}
