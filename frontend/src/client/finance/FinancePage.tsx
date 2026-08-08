// Finance module UI (docs/modules/FINANCE.md). Posting is one-way: a draft can
// be edited, a posted document can only be voided — the UI mirrors that.

import { useLocation, useOutletContext } from "react-router-dom";
import { csvGrants } from "../../shared/csv/access";
import { ImportApprovals } from "../../shared/csv/ImportApprovals";
import { PageHeader } from "../../shared/shell";
import type { ClientMe } from "../../shared/types";
import { Stack, Tabs, TabsContent, TabsList, TabsTrigger } from "../../shared/ui";
import { BillsSection } from "./BillsSection";
import { ChartSection } from "./ChartSection";
import { FinanceAnalytics } from "./FinanceAnalytics";
import { InvoicesSection } from "./InvoicesSection";
import { ReportsSection } from "./ReportsSection";

export function FinancePage() {
  const me = useOutletContext<ClientMe>();
  const { pathname } = useLocation();
  const canWrite = (me.role.permissions["finance"] ?? 0) >= 3;
  const canAnalytics = (me.role.permissions["finance_analytics"] ?? 0) >= 1;
  const csv = (entity: string) => csvGrants(me, "finance", entity);

  // Dashboard quick actions deep-link to /app/finance/<section>[/new]: pick the
  // tab from the path and open the create modal when the path ends in /new.
  const tab = pathname.startsWith("/app/finance/bills") ? "bills"
    : pathname.startsWith("/app/finance/reports") ? "reports"
    : pathname.startsWith("/app/finance/chart") ? "chart"
    : "invoices";
  const isNew = pathname.endsWith("/new");

  return (
    <Stack>
      <PageHeader title="Finance" description="Receivables, payables, and the ledger behind them" />

      <ImportApprovals me={me} module="finance" />

      <Tabs defaultValue={tab}>
        <TabsList>
          <TabsTrigger value="invoices">Invoices</TabsTrigger>
          <TabsTrigger value="bills">Bills</TabsTrigger>
          <TabsTrigger value="reports">Reports</TabsTrigger>
          <TabsTrigger value="chart">Chart of accounts</TabsTrigger>
          {canAnalytics && <TabsTrigger value="analytics">Analytics</TabsTrigger>}
        </TabsList>

        <TabsContent value="invoices">
          <InvoicesSection canWrite={canWrite} csv={csv("invoices")}
            openNew={tab === "invoices" && isNew} />
        </TabsContent>
        <TabsContent value="bills">
          <BillsSection canWrite={canWrite} csv={csv("bills")}
            openNew={tab === "bills" && isNew} />
        </TabsContent>
        <TabsContent value="reports"><ReportsSection /></TabsContent>
        <TabsContent value="chart">
          <ChartSection canWrite={canWrite} csv={csv("accounts")} />
        </TabsContent>
        {canAnalytics && (
          <TabsContent value="analytics"><FinanceAnalytics /></TabsContent>
        )}
      </Tabs>
    </Stack>
  );
}
