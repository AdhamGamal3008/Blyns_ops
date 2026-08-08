// Projects Analytics / Overview tab (docs/PROJECT_ANALYTICS_PLAN.md §5).
//
// Fetches /projects/analytics and renders a headline KPI row plus decision-grade
// charts. The server tiers the payload by role — VIEW returns only `kpis`, READ
// adds the chart blocks — so each chart renders ONLY IF its block is present (and
// carries data). That means this component never needs to know the caller's level.

import { AlarmClock, FileWarning, FolderKanban, PauseCircle, Wallet } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import type { ProjectAnalytics } from "../../shared/types";
import { BarChart, DataState, Grid, KpiCard, Stack, TrendChart } from "../../shared/ui";
import {
  ChartCard, GOLD, GOOD, INFO, INK, int, money, moneyShort, rows, sum,
} from "../analytics/parts";
import { humanize } from "./types";

function budgetHint(b: ProjectAnalytics["kpis"]["budget"]): string {
  const side = b.variance <= 0 ? "under" : "over";
  const pct = b.variance_pct == null ? "" : `${Math.abs(b.variance_pct)}% ${side} · `;
  return `${pct}${money(b.actual)} of ${money(b.planned)}`;
}

export function ProjectsAnalytics() {
  const [data, setData] = useState<ProjectAnalytics | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    setError(null);
    api<ProjectAnalytics>("/projects/analytics")
      .then((r) => setData(r.data))
      .catch(setError);
  }, []);
  useEffect(load, [load]);

  return (
    <DataState loading={!data && !error} error={data ? null : error} onRetry={load}>
      {data && <Body data={data} />}
    </DataState>
  );
}

function Body({ data }: { data: ProjectAnalytics }) {
  const k = data.kpis;

  const byStage = data.by_stage ?? [];
  const timeInStage = data.time_in_stage ?? [];
  const topProjects = data.budget?.top_projects ?? [];
  const costByType = (data.budget?.cost_by_type ?? []).map((c) => ({
    ...c, label: humanize(c.cost_type),
  }));
  const exceptions = (data.exceptions ?? []).map((e) => ({ ...e, label: humanize(e.type) }));
  const throughput = data.throughput ?? [];

  const showStage = sum(byStage.map((s) => s.count)) > 0;
  const showTime = timeInStage.length > 0;
  const showTop = topProjects.length > 0;
  const showCost = sum(costByType.map((c) => c.amount)) > 0;
  const showExc = exceptions.length > 0;
  const showThr = sum(throughput.map((t) => t.started + t.completed)) > 0;

  return (
    <Stack gap={5}>
      <Grid min={180}>
        <KpiCard label="Active" value={int(k.active)} icon={<FolderKanban size={18} />} />
        <KpiCard label="On hold / blocked" value={int(k.on_hold_blocked)}
          icon={<PauseCircle size={18} />} />
        <KpiCard label="Overdue" value={int(k.overdue)} icon={<AlarmClock size={18} />} />
        <KpiCard label="Open exceptions" value={int(k.open_exceptions)}
          icon={<FileWarning size={18} />} />
        <KpiCard label="Budget variance" value={money(k.budget.variance)}
          hint={budgetHint(k.budget)} icon={<Wallet size={18} />} />
      </Grid>

      <Grid min={380}>
        {showStage && (
          <ChartCard title="Active projects by stage"
            description="Where the live portfolio is piling up">
            <BarChart data={rows(byStage)} xKey="label"
              series={[{ key: "count", label: "Active projects", color: INK }]}
              formatValue={int} />
          </ChartCard>
        )}

        {showTime && (
          <ChartCard title="Average days in current stage"
            description="Bottlenecks — how long active work has sat">
            <BarChart data={rows(timeInStage)} xKey="label"
              series={[{ key: "avg_days", label: "Avg days", color: INK }]}
              formatValue={(n) => `${n}d`} />
          </ChartCard>
        )}

        {showTop && (
          <ChartCard title="Planned vs actual — top projects"
            legend={[{ label: "Planned", color: INFO }, { label: "Actual", color: INK }]}>
            <BarChart data={rows(topProjects)} xKey="code" formatValue={moneyShort}
              series={[
                { key: "planned", label: "Planned", color: INFO },
                { key: "actual", label: "Actual", color: INK },
              ]} />
          </ChartCard>
        )}

        {showCost && (
          <ChartCard title="Cost by type" description="Where actual spend goes">
            <BarChart data={rows(costByType)} xKey="label" formatValue={moneyShort}
              series={[{ key: "amount", label: "Cost", color: GOLD }]} />
          </ChartCard>
        )}

        {showExc && (
          <ChartCard title="Open exceptions by type"
            legend={[{ label: "Open", color: INK }, { label: "In progress", color: GOLD }]}>
            <BarChart data={rows(exceptions)} xKey="label" stacked formatValue={int}
              series={[
                { key: "open", label: "Open", color: INK },
                { key: "in_progress", label: "In progress", color: GOLD },
              ]} />
          </ChartCard>
        )}

        {showThr && (
          <ChartCard title="Throughput — last 6 months"
            legend={[{ label: "Started", color: INFO }, { label: "Completed", color: GOOD }]}>
            <TrendChart data={rows(throughput)} xKey="month" formatValue={int}
              series={[
                { key: "started", label: "Started", color: INFO },
                { key: "completed", label: "Completed", color: GOOD },
              ]} />
          </ChartCard>
        )}
      </Grid>
    </Stack>
  );
}
