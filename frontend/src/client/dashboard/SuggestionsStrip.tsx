// Contextual "next step" strip (Phase 3): data-state nudges the server decides
// this user can act on — draft invoices to send, low stock to reorder, overdue
// milestones, new leads. Each is a Banner with a deep-link CTA and a dismiss;
// dismissing is per-user and resurfaces later (server-side TTL / signal growth).

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../shared/api";
import type { Suggestion } from "../../shared/types";
import { Banner, Button, Stack } from "../../shared/ui";

export function SuggestionsStrip() {
  const navigate = useNavigate();
  const [items, setItems] = useState<Suggestion[] | null>(null);

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
      load(); // dismissal failed — put the strip back as the server sees it
    }
  }

  if (!items || items.length === 0) return null;

  return (
    <Stack gap={2}>
      {items.map((s) => (
        <Banner
          key={s.key}
          tone="info"
          onDismiss={() => dismiss(s.key)}
          action={
            <Button variant="secondary" size="compact" onClick={() => navigate(s.target_route)}>
              {s.cta_label}
            </Button>
          }
        >
          {s.message}
        </Banner>
      ))}
    </Stack>
  );
}
