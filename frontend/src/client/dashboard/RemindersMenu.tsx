// Reminders bell for the top bar. Houses the same data-state "next step" nudges
// that used to render as a strip on the dashboard — draft invoices to send, low
// stock to reorder, overdue milestones, new leads. The server decides what this
// user can act on; each row deep-links, and dismissing is per-user and resurfaces
// later (server-side TTL / signal growth). Living in the shell instead of the
// dashboard body means the reminders follow the user across every screen.

import { Bell, Check, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../shared/api";
import type { Suggestion } from "../../shared/types";
import { Button, Popover, Spinner } from "../../shared/ui";
import styles from "./RemindersMenu.module.css";

export function RemindersMenu() {
  const navigate = useNavigate();
  const [items, setItems] = useState<Suggestion[] | null>(null);
  const [open, setOpen] = useState(false);

  const load = useCallback(() => {
    api<Suggestion[]>("/dashboard/suggestions")
      .then((res) => setItems(res.data))
      .catch(() => setItems([]));
  }, []);

  useEffect(() => load(), [load]);

  async function dismiss(key: string) {
    // Drop it immediately, then reconcile with the server's fresh list.
    setItems((cur) => cur?.filter((s) => s.key !== key) ?? cur);
    try {
      const res = await api<Suggestion[]>(
        `/dashboard/suggestions/${key}/dismiss`, { method: "POST" });
      setItems(res.data);
    } catch {
      load(); // dismissal failed — put the list back as the server sees it
    }
  }

  function act(route: string) {
    setOpen(false); // close the panel before the route change lands
    navigate(route);
  }

  const count = items?.length ?? 0;

  const trigger = (
    <button
      type="button"
      className={styles.trigger}
      aria-label={count > 0 ? `Reminders, ${count} pending` : "Reminders"}
    >
      <Bell size={20} aria-hidden="true" />
      {count > 0 && (
        <span className={styles.count} aria-hidden="true">
          {count > 9 ? "9+" : count}
        </span>
      )}
    </button>
  );

  return (
    <Popover
      trigger={trigger}
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) load(); // refresh each time it opens — the shell is long-lived
      }}
      side="bottom"
      align="end"
      size="lg"
      contentProps={{ "aria-label": "Reminders" }}
    >
      <div className={styles.panel}>
        <div className={styles.header}>
          <p className={styles.heading}>Reminders</p>
          {count > 0 && <span className={styles.badge}>{count}</span>}
        </div>

        {items === null ? (
          <div className={styles.status}>
            <Spinner size="sm" />
          </div>
        ) : items.length === 0 ? (
          <div className={styles.empty}>
            <span className={styles.emptyIcon} aria-hidden="true">
              <Check size={20} />
            </span>
            <p className={styles.emptyText}>You&rsquo;re all caught up.</p>
          </div>
        ) : (
          <ul className={styles.list}>
            {items.map((s) => (
              <li key={s.key} className={styles.item}>
                <p className={styles.message}>{s.message}</p>
                <div className={styles.actions}>
                  <Button
                    variant="secondary"
                    size="compact"
                    onClick={() => act(s.target_route)}
                  >
                    {s.cta_label}
                  </Button>
                  <button
                    type="button"
                    className={styles.dismiss}
                    onClick={() => dismiss(s.key)}
                    aria-label={`Dismiss: ${s.message}`}
                  >
                    <X size={16} aria-hidden="true" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Popover>
  );
}
