// CRM Analytics / Overview tab (docs/PROJECT_ANALYTICS_PLAN.md §6-D).
//
// Same contract as the Projects analytics tab: the server tiers the payload by
// role (VIEW = kpis only, READ = + charts), so each chart renders only if its
// block is present and carries data.

import { Building2, Handshake, Trophy, UserPlus, Wallet } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import type { CrmAnalytics as CrmData } from "../../shared/types";
import { BarChart, DataState, Grid, KpiCard, Stack, TrendChart } from "../../shared/ui";
import {
  ChartCard, GOLD, INFO, INK, int, money, moneyShort, rows, sum,
} from "../analytics/parts";

export function CrmAnalytics() {
  const [data, setData] = useState<CrmData | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    setError(null);
    api<CrmData>("/crm/analytics").then((r) => setData(r.data)).catch(setError);
  }, []);
  useEffect(load, [load]);

  return (
    <DataState loading={!data && !error} error={data ? null : error} onRetry={load}>
      {data && <Body data={data} />}
    </DataState>
  );
}

function Body({ data }: { data: CrmData }) {
  const k = data.kpis;

  const pipeline = data.pipeline_by_stage ?? [];
  const leadStatus = data.lead_status ?? [];
  const leadSources = data.lead_sources ?? [];
  const topDeals = data.top_deals ?? [];
  const inflow = data.inflow ?? [];

  const showPipeline = sum(pipeline.map((s) => s.amount + s.count)) > 0;
  const showLeadStatus = sum(leadStatus.map((s) => s.count)) > 0;
  const showSources = sum(leadSources.map((s) => s.count)) > 0;
  const showTopDeals = topDeals.length > 0;
  const showInflow = sum(inflow.map((m) => m.leads + m.deals)) > 0;

  return (
    <Stack gap={5}>
      <Grid min={180}>
        <KpiCard label="Open deals" value={int(k.open_deals)} icon={<Handshake size={18} />} />
        <KpiCard label="Pipeline value" value={money(k.pipeline_value)}
          hint={`${money(k.pipeline_weighted)} weighted`} icon={<Wallet size={18} />} />
        <KpiCard label="Win rate" value={k.win_rate == null ? "—" : `${k.win_rate}%`}
          icon={<Trophy size={18} />} />
        <KpiCard label="Open leads" value={int(k.open_leads)} icon={<UserPlus size={18} />} />
        <KpiCard label="Customers" value={int(k.customers)} icon={<Building2 size={18} />} />
      </Grid>

      <Grid min={380}>
        {showPipeline && (
          <ChartCard title="Open pipeline by stage" description="Where the deal value sits">
            <BarChart data={rows(pipeline)} xKey="label" formatValue={moneyShort}
              series={[{ key: "amount", label: "Pipeline value", color: INK }]} />
          </ChartCard>
        )}

        {showLeadStatus && (
          <ChartCard title="Leads by status" description="Top-of-funnel health">
            <BarChart data={rows(leadStatus)} xKey="label" formatValue={int}
              series={[{ key: "count", label: "Leads", color: INK }]} />
          </ChartCard>
        )}

        {showSources && (
          <ChartCard title="Lead sources" description="Which channels bring leads in">
            <BarChart data={rows(leadSources)} xKey="source" formatValue={int}
              series={[{ key: "count", label: "Leads", color: GOLD }]} />
          </ChartCard>
        )}

        {showTopDeals && (
          <ChartCard title="Top open deals" description="Biggest live opportunities">
            <BarChart data={rows(topDeals)} xKey="title" formatValue={moneyShort}
              series={[{ key: "amount", label: "Amount", color: INK }]} />
          </ChartCard>
        )}

        {showInflow && (
          <ChartCard title="New leads vs deals — last 6 months"
            legend={[{ label: "New leads", color: INFO }, { label: "New deals", color: INK }]}>
            <TrendChart data={rows(inflow)} xKey="month" formatValue={int}
              series={[
                { key: "leads", label: "New leads", color: INFO },
                { key: "deals", label: "New deals", color: INK },
              ]} />
          </ChartCard>
        )}
      </Grid>
    </Stack>
  );
}
