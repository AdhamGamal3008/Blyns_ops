// Inventory Analytics / Overview tab (docs/PROJECT_ANALYTICS_PLAN.md §6-D).
//
// Same contract as the other modules: the server tiers the payload by role
// (VIEW = kpis only, READ = + charts), so each chart renders only if its block
// is present and carries data.

import { Package, PackageMinus, PackageX, Tags, Wallet } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import type { InventoryAnalytics as InvData } from "../../shared/types";
import { BarChart, DataState, Grid, KpiCard, Stack, TrendChart } from "../../shared/ui";
import {
  ChartCard, GOLD, GOOD, INK, int, money, moneyShort, rows, sum,
} from "../analytics/parts";

export function InventoryAnalytics() {
  const [data, setData] = useState<InvData | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    setError(null);
    api<InvData>("/inventory/analytics").then((r) => setData(r.data)).catch(setError);
  }, []);
  useEffect(load, [load]);

  return (
    <DataState loading={!data && !error} error={data ? null : error} onRetry={load}>
      {data && <Body data={data} />}
    </DataState>
  );
}

function Body({ data }: { data: InvData }) {
  const k = data.kpis;

  const byCategory = data.value_by_category ?? [];
  const lowStock = data.low_stock_items ?? [];
  const topProducts = data.top_products ?? [];
  const movements = data.movements ?? [];
  const status = data.stock_status ?? [];

  const showCategory = sum(byCategory.map((c) => c.value)) > 0;
  const showLow = lowStock.length > 0;
  const showTop = sum(topProducts.map((p) => p.value)) > 0;
  const showMovements = sum(movements.map((m) => m.received + m.issued)) > 0;
  const showStatus = sum(status.map((s) => s.count)) > 0;

  return (
    <Stack gap={5}>
      <Grid min={180}>
        <KpiCard label="Active SKUs" value={int(k.active_skus)} icon={<Package size={18} />} />
        <KpiCard label="Stock value" value={money(k.stock_value)} icon={<Wallet size={18} />} />
        <KpiCard label="Low stock" value={int(k.low_stock)} icon={<PackageMinus size={18} />} />
        <KpiCard label="Out of stock" value={int(k.out_of_stock)} icon={<PackageX size={18} />} />
        <KpiCard label="Categories" value={int(k.categories)} icon={<Tags size={18} />} />
      </Grid>

      <Grid min={380}>
        {showCategory && (
          <ChartCard title="Stock value by category" description="Where capital is tied up">
            <BarChart data={rows(byCategory)} xKey="category" formatValue={moneyShort}
              series={[{ key: "value", label: "Stock value", color: INK }]} />
          </ChartCard>
        )}

        {showLow && (
          <ChartCard title="Low-stock items"
            legend={[{ label: "On hand", color: INK }, { label: "Reorder point", color: GOLD }]}>
            <BarChart data={rows(lowStock)} xKey="sku" formatValue={int}
              series={[
                { key: "on_hand", label: "On hand", color: INK },
                { key: "reorder", label: "Reorder point", color: GOLD },
              ]} />
          </ChartCard>
        )}

        {showMovements && (
          <ChartCard title="Stock movements — last 6 months"
            legend={[{ label: "Received", color: GOOD }, { label: "Issued", color: INK }]}>
            <TrendChart data={rows(movements)} xKey="month" formatValue={int}
              series={[
                { key: "received", label: "Received", color: GOOD },
                { key: "issued", label: "Issued", color: INK },
              ]} />
          </ChartCard>
        )}

        {showTop && (
          <ChartCard title="Top products by value" description="Biggest holdings">
            <BarChart data={rows(topProducts)} xKey="sku" formatValue={moneyShort}
              series={[{ key: "value", label: "Stock value", color: INK }]} />
          </ChartCard>
        )}

        {showStatus && (
          <ChartCard title="Stock status" description="Configured items by health">
            <BarChart data={rows(status)} xKey="status" formatValue={int}
              series={[{ key: "count", label: "Items", color: GOLD }]} />
          </ChartCard>
        )}
      </Grid>
    </Stack>
  );
}
