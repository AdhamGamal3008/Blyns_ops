// Headline KPIs (§1) — a KPI the user's role cannot READ is simply absent.

import { AlertTriangle, FolderKanban, Handshake, PackageMinus, Receipt } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "../../shared/api";
import type { KpiSet } from "../../shared/types";
import { Grid, KpiCard } from "../../shared/ui";
import { companyCurrency } from "../../shared/currency";

const KPI_DEFS: {
  key: keyof KpiSet;
  label: string;
  money?: boolean;
  icon: ReactNode;
}[] = [
  { key: "open_projects", label: "Open projects", icon: <FolderKanban size={18} /> },
  { key: "overdue_tasks", label: "Overdue tasks", icon: <AlertTriangle size={18} /> },
  { key: "open_deals", label: "Open deals", icon: <Handshake size={18} /> },
  { key: "low_stock_items", label: "Low stock items", icon: <PackageMinus size={18} /> },
  {
    key: "unpaid_invoices_total",
    label: "Unpaid invoices",
    money: true,
    icon: <Receipt size={18} />,
  },
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
    <Grid min={196}>
      {visible.map((d) => {
        const n = Number(kpis[d.key]);
        return (
          <KpiCard
            key={d.key}
            label={d.label}
            icon={d.icon}
            value={
              d.money
                ? n.toLocaleString(undefined, {
                    style: "currency",
                    currency: companyCurrency(),
                    maximumFractionDigits: 0,
                  })
                : n.toLocaleString()
            }
          />
        );
      })}
    </Grid>
  );
}
