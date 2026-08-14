// Production Analytics / Overview tab (docs/PRODUCTION_MODULE_PLAN.md §7 Phase 5).
//
// Same contract as the other modules: the server tiers the payload by role
// (VIEW = kpis only, READ = + charts), so each chart renders only if its block
// is present and carries data. No cost is ever shown (plan D3).

import { Clock, Gauge, Layers, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import type { ProductionAnalytics as ProdData } from "../../shared/types";
import { BarChart, DataState, Grid, KpiCard, Stack, TrendChart } from "../../shared/ui";
import { ChartCard, GOLD, INFO, INK, int, rows, sum } from "../analytics/parts";

const pct = (n: number | null) => (n == null ? "—" : `${n}%`);

export function ProductionAnalytics() {
  const [data, setData] = useState<ProdData | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    setError(null);
    api<ProdData>("/production/analytics").then((r) => setData(r.data)).catch(setError);
  }, []);
  useEffect(load, [load]);

  return (
    <DataState loading={!data && !error} error={data ? null : error} onRetry={load}>
      {data && <Body data={data} />}
    </DataState>
  );
}

function Body({ data }: { data: ProdData }) {
  const k = data.kpis;

  const byStatus = data.by_status ?? [];
  const byStation = data.by_station ?? [];
  const throughput = data.throughput ?? [];

  const showStatus = sum(byStatus.map((s) => s.count)) > 0;
  const showStation = sum(byStation.map((s) => s.open)) > 0;
  const showThroughput = sum(throughput.map((t) => t.dispatched)) > 0;

  return (
    <Stack gap={5}>
      <Grid min={180}>
        <KpiCard label="Throughput (30d)" value={int(k.throughput)} icon={<Gauge size={18} />} />
        <KpiCard label="On-time" value={pct(k.on_time_pct)} icon={<Clock size={18} />} />
        <KpiCard label="Work in progress" value={int(k.wip)} icon={<Layers size={18} />} />
        <KpiCard label="Hold rate" value={pct(k.hold_rate)} icon={<TriangleAlert size={18} />} />
      </Grid>

      <Grid min={380}>
        {showStatus && (
          <ChartCard title="Work orders by status" description="Where work sits in the lifecycle">
            <BarChart data={rows(byStatus)} xKey="status" formatValue={int}
              series={[{ key: "count", label: "Work orders", color: INK }]} />
          </ChartCard>
        )}

        {showStation && (
          <ChartCard title="Open work by station" description="Live load across work centres">
            <BarChart data={rows(byStation)} xKey="station" formatValue={int}
              series={[{ key: "open", label: "Open work orders", color: GOLD }]} />
          </ChartCard>
        )}

        {showThroughput && (
          <ChartCard title="Throughput — last 6 months" description="Work orders dispatched">
            <TrendChart data={rows(throughput)} xKey="month" formatValue={int}
              series={[{ key: "dispatched", label: "Dispatched", color: INFO }]} />
          </ChartCard>
        )}
      </Grid>
    </Stack>
  );
}
