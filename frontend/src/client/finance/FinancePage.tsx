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
import { InvoicesSection } from "./InvoicesSection";
import { ReportsSection } from "./ReportsSection";

export function FinancePage() {
  const me = useOutletContext<ClientMe>();
  const location = useLocation();
  // the dashboard's `finance.invoice.new` quick action deep-links here
  const newInvoice = location.pathname.endsWith("/invoices/new");
  const canWrite = (me.role.permissions["finance"] ?? 0) >= 3;
  const csv = (entity: string) => csvGrants(me, "finance", entity);

  return (
    <Stack>
      <PageHeader title="Finance" description="Receivables, payables, and the ledger behind them" />

      <ImportApprovals me={me} module="finance" />

      <Tabs defaultValue="invoices">
        <TabsList>
          <TabsTrigger value="invoices">Invoices</TabsTrigger>
          <TabsTrigger value="bills">Bills</TabsTrigger>
          <TabsTrigger value="reports">Reports</TabsTrigger>
          <TabsTrigger value="chart">Chart of accounts</TabsTrigger>
        </TabsList>

        <TabsContent value="invoices">
          <InvoicesSection canWrite={canWrite} csv={csv("invoices")} openNew={newInvoice} />
        </TabsContent>
        <TabsContent value="bills">
          <BillsSection canWrite={canWrite} csv={csv("bills")} />
        </TabsContent>
        <TabsContent value="reports"><ReportsSection /></TabsContent>
        <TabsContent value="chart">
          <ChartSection canWrite={canWrite} csv={csv("accounts")} />
        </TabsContent>
      </Tabs>
    </Stack>
  );
}
