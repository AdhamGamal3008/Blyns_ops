// Headline KPIs (§1) — a KPI the user's role cannot READ is simply absent.

import { useEffect, useState } from "react";
import { api } from "../../shared/api";
import type { KpiSet } from "../../shared/types";
import { Card } from "../../shared/ui";

const KPI_DEFS: { key: keyof KpiSet; label: string; money?: boolean }[] = [
  { key: "open_projects", label: "Open projects" },
  { key: "overdue_tasks", label: "Overdue tasks" },
  { key: "open_deals", label: "Open deals" },
  { key: "low_stock_items", label: "Low stock items" },
  { key: "unpaid_invoices_total", label: "Unpaid invoices", money: true },
];

export function KpiCards() {
  const [kpis, setKpis] = useState<KpiSet | null>(null);

  useEffect(() => {
    api<KpiSet>("/dashboard/kpis")
      .then((res) => setKpis(res.data))
      .catch(() => setKpis({}));
  }, []);

  if (!kpis) return null;
  const visible = KPI_DEFS.filter((d) => kpis[d.key] !== undefined);
  if (visible.length === 0) return null;

  return (
    <div className="kpi-grid">
      {visible.map((d) => (
        <Card key={d.key} className="kpi">
          <div className="kpi-label">{d.label}</div>
          <div className="kpi-value">
            {d.money
              ? `$${Number(kpis[d.key]).toLocaleString()}`
              : Number(kpis[d.key]).toLocaleString()}
          </div>
        </Card>
      ))}
    </div>
  );
}
