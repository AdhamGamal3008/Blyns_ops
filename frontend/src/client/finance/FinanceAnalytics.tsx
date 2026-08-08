// Finance Analytics / Overview tab (docs/PROJECT_ANALYTICS_PLAN.md §6-D).
//
// Same contract as the other modules: the server tiers the payload by role
// (VIEW = kpis only, READ = + charts), so each chart renders only if its block
// is present and carries data.

import { AlertTriangle, CreditCard, Receipt, TrendingDown, TrendingUp } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import type { FinanceAnalytics as FinData } from "../../shared/types";
import { BarChart, DataState, Grid, KpiCard, Stack, TrendChart } from "../../shared/ui";
import {
  ChartCard, GOLD, GOOD, INK, money, moneyShort, rows, sum,
} from "../analytics/parts";

export function FinanceAnalytics() {
  const [data, setData] = useState<FinData | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    setError(null);
    api<FinData>("/finance/analytics").then((r) => setData(r.data)).catch(setError);
  }, []);
  useEffect(load, [load]);

  return (
    <DataState loading={!data && !error} error={data ? null : error} onRetry={load}>
      {data && <Body data={data} />}
    </DataState>
  );
}

function Body({ data }: { data: FinData }) {
  const k = data.kpis;

  const invoices = data.invoices_by_status ?? [];
  const bills = data.bills_by_status ?? [];
  const aging = data.ar_aging ?? [];
  const overdue = data.top_overdue ?? [];
  const cashflow = data.cashflow ?? [];

  const showInvoices = sum(invoices.map((r) => r.amount)) > 0;
  const showBills = sum(bills.map((r) => r.amount)) > 0;
  const showAging = sum(aging.map((r) => r.amount)) > 0;
  const showOverdue = overdue.length > 0;
  const showCashflow = sum(cashflow.map((m) => m.revenue + m.expenses)) > 0;

  return (
    <Stack gap={5}>
      <Grid min={180}>
        <KpiCard label="Revenue" value={money(k.revenue)} icon={<TrendingUp size={18} />} />
        <KpiCard label="Expenses" value={money(k.expenses)} icon={<TrendingDown size={18} />} />
        <KpiCard label="AR outstanding" value={money(k.ar_outstanding)}
          icon={<Receipt size={18} />} />
        <KpiCard label="AP outstanding" value={money(k.ap_outstanding)}
          icon={<CreditCard size={18} />} />
        <KpiCard label="Overdue AR" value={money(k.overdue_ar)}
          icon={<AlertTriangle size={18} />} />
      </Grid>

      <Grid min={380}>
        {showInvoices && (
          <ChartCard title="Invoices by status" description="AR composition">
            <BarChart data={rows(invoices)} xKey="status" formatValue={moneyShort}
              series={[{ key: "amount", label: "Invoiced", color: INK }]} />
          </ChartCard>
        )}

        {showBills && (
          <ChartCard title="Bills by status" description="AP composition">
            <BarChart data={rows(bills)} xKey="status" formatValue={moneyShort}
              series={[{ key: "amount", label: "Billed", color: GOLD }]} />
          </ChartCard>
        )}

        {showAging && (
          <ChartCard title="AR aging" description="Outstanding by age">
            <BarChart data={rows(aging)} xKey="bucket" formatValue={moneyShort}
              series={[{ key: "amount", label: "Outstanding", color: INK }]} />
          </ChartCard>
        )}

        {showOverdue && (
          <ChartCard title="Top overdue invoices" description="Who to chase first">
            <BarChart data={rows(overdue)} xKey="number" formatValue={moneyShort}
              series={[{ key: "outstanding", label: "Outstanding", color: INK }]} />
          </ChartCard>
        )}

        {showCashflow && (
          <ChartCard title="Revenue vs expenses — last 6 months"
            legend={[{ label: "Revenue", color: GOOD }, { label: "Expenses", color: INK }]}>
            <TrendChart data={rows(cashflow)} xKey="month" formatValue={moneyShort}
              series={[
                { key: "revenue", label: "Revenue", color: GOOD },
                { key: "expenses", label: "Expenses", color: INK },
              ]} />
          </ChartCard>
        )}
      </Grid>
    </Stack>
  );
}
