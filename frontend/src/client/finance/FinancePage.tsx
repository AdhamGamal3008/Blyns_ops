// Finance module UI (docs/modules/FINANCE.md). Posting is one-way: a draft can
// be edited, a posted document can only be voided — the UI mirrors that.

import { useLocation, useOutletContext } from "react-router-dom";
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

  return (
    <Stack>
      <PageHeader title="Finance" description="Receivables, payables, and the ledger behind them" />

      <Tabs defaultValue="invoices">
        <TabsList>
          <TabsTrigger value="invoices">Invoices</TabsTrigger>
          <TabsTrigger value="bills">Bills</TabsTrigger>
          <TabsTrigger value="reports">Reports</TabsTrigger>
          <TabsTrigger value="chart">Chart of accounts</TabsTrigger>
        </TabsList>

        <TabsContent value="invoices">
          <InvoicesSection canWrite={canWrite} openNew={newInvoice} />
        </TabsContent>
        <TabsContent value="bills"><BillsSection canWrite={canWrite} /></TabsContent>
        <TabsContent value="reports"><ReportsSection /></TabsContent>
        <TabsContent value="chart"><ChartSection canWrite={canWrite} /></TabsContent>
      </Tabs>
    </Stack>
  );
}
