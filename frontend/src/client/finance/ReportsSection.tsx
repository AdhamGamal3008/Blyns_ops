// Reports (§2): trial balance, P&L, balance sheet, AR/AP aging. The balance
// checks are surfaced, not hidden — a book that stops balancing should be
// visible at a glance.

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api } from "../../shared/api";
import {
  Badge,
  Card,
  CardHeader,
  DataState,
  DataTable,
  type DataTableColumn,
  Grid,
  KpiCard,
  Stack,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../shared/ui";
import {
  money,
  type Aging,
  type AgingItem,
  type BalanceSheet,
  type Pnl,
  type TrialBalance,
  type TrialBalanceRow,
} from "./types";
import styles from "./Finance.module.css";

export function ReportsSection() {
  return (
    <Tabs defaultValue="trial-balance">
      <TabsList>
        <TabsTrigger value="trial-balance">Trial balance</TabsTrigger>
        <TabsTrigger value="pnl">Profit &amp; loss</TabsTrigger>
        <TabsTrigger value="balance-sheet">Balance sheet</TabsTrigger>
        <TabsTrigger value="ar">AR aging</TabsTrigger>
        <TabsTrigger value="ap">AP aging</TabsTrigger>
      </TabsList>

      <TabsContent value="trial-balance"><TrialBalanceReport /></TabsContent>
      <TabsContent value="pnl"><PnlReport /></TabsContent>
      <TabsContent value="balance-sheet"><BalanceSheetReport /></TabsContent>
      <TabsContent value="ar"><AgingReport kind="ar" /></TabsContent>
      <TabsContent value="ap"><AgingReport kind="ap" /></TabsContent>
    </Tabs>
  );
}

function useReport<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(() => {
    setError(null);
    api<T>(path).then((r) => setData(r.data)).catch(setError);
  }, [path]);
  useEffect(load, [load]);
  return { data, error, reload: load };
}

/** Whether the books balance is the headline, not a footnote. */
function BalanceBadge({ balanced }: { balanced: boolean }) {
  return (
    <Badge tone={balanced ? "success" : "danger"} variant={balanced ? "soft" : "solid"}>
      {balanced ? "balanced" : "out of balance"}
    </Badge>
  );
}

function StatementRow(props: { label: ReactNode; value: ReactNode; indent?: boolean; total?: boolean }) {
  return (
    <tr className={props.total ? styles.totalRow : undefined}>
      <td style={props.indent ? { paddingLeft: "var(--sp-6)" } : undefined}>{props.label}</td>
      <td className={styles.num}>{props.value}</td>
    </tr>
  );
}

export function TrialBalanceReport() {
  const { data, error, reload } = useReport<TrialBalance>("/finance/reports/trial-balance");

  const columns: DataTableColumn<TrialBalanceRow>[] = [
    { key: "code", header: "Code", sortable: true },
    { key: "name", header: "Account", sortable: true, accessor: (r) => <b>{r.name}</b> },
    { key: "type", header: "Type", sortable: true },
    {
      key: "debit",
      header: "Debit",
      numeric: true,
      sortable: true,
      accessor: (r) => (r.debit ? money(r.debit) : "—"),
      sortValue: (r) => r.debit,
    },
    {
      key: "credit",
      header: "Credit",
      numeric: true,
      sortable: true,
      accessor: (r) => (r.credit ? money(r.credit) : "—"),
      sortValue: (r) => r.credit,
    },
  ];

  return (
    <section>
      <CardHeader
        title="Trial balance"
        description={
          data ? `Debits ${money(data.debit_total)} · Credits ${money(data.credit_total)}` : undefined
        }
        actions={data && <BalanceBadge balanced={data.balanced} />}
      />
      <DataState
        loading={!data && !error}
        error={data ? null : error}
        onRetry={reload}
        isEmpty={data?.rows.length === 0}
        emptyTitle="Nothing posted yet"
      >
        <DataTable
          data={data?.rows ?? []}
          columns={columns}
          getRowId={(r) => r.account_id}
          pageSize={20}
          searchPlaceholder="Search accounts…"
        />
      </DataState>
    </section>
  );
}

function PnlReport() {
  const { data, error, reload } = useReport<Pnl>("/finance/reports/pnl");

  return (
    <section>
      <CardHeader title="Profit &amp; loss" />
      <DataState loading={!data && !error} error={data ? null : error} onRetry={reload}>
        {data && (
          <Stack gap={4}>
            <Grid min={200}>
              <KpiCard label="Income" value={money(data.income_total)} />
              <KpiCard label="Expense" value={money(data.expense_total)} />
              <KpiCard
                label="Net profit"
                value={money(data.net_profit)}
                delta={{
                  value: data.income_total
                    ? `${Math.round((data.net_profit / data.income_total) * 100)}% margin`
                    : "—",
                  direction: data.net_profit >= 0 ? "up" : "down",
                }}
              />
            </Grid>

            <Card padded={false}>
              <table className={styles.statement}>
                <tbody>
                  <tr><th colSpan={2}>Income</th></tr>
                  {data.income.map((r) => (
                    <StatementRow key={r.account_id} indent label={r.name} value={money(r.amount)} />
                  ))}
                  <StatementRow total label="Total income" value={money(data.income_total)} />

                  <tr><th colSpan={2}>Expense</th></tr>
                  {data.expense.map((r) => (
                    <StatementRow key={r.account_id} indent label={r.name} value={money(r.amount)} />
                  ))}
                  <StatementRow total label="Total expense" value={money(data.expense_total)} />

                  <StatementRow total label="Net profit" value={money(data.net_profit)} />
                </tbody>
              </table>
            </Card>
          </Stack>
        )}
      </DataState>
    </section>
  );
}

function BalanceSheetReport() {
  const { data, error, reload } = useReport<BalanceSheet>("/finance/reports/balance-sheet");

  return (
    <section>
      <CardHeader
        title="Balance sheet"
        actions={data && <BalanceBadge balanced={data.balanced} />}
      />
      <DataState loading={!data && !error} error={data ? null : error} onRetry={reload}>
        {data && (
          <Card padded={false}>
            <table className={styles.statement}>
              <tbody>
                <tr><th colSpan={2}>Assets</th></tr>
                {data.assets.map((r) => (
                  <StatementRow key={r.account_id} indent label={r.name} value={money(r.balance)} />
                ))}
                <StatementRow total label="Total assets" value={money(data.assets_total)} />

                <tr><th colSpan={2}>Liabilities</th></tr>
                {data.liabilities.map((r) => (
                  <StatementRow key={r.account_id} indent label={r.name} value={money(-r.balance)} />
                ))}

                <tr><th colSpan={2}>Equity</th></tr>
                {data.equity.map((r) => (
                  <StatementRow key={r.account_id} indent label={r.name} value={money(-r.balance)} />
                ))}
                <StatementRow
                  indent
                  label="Retained earnings (this period)"
                  value={money(data.retained_earnings)}
                />

                <StatementRow
                  total
                  label="Liabilities + equity"
                  value={money(data.liabilities_and_equity_total)}
                />
              </tbody>
            </table>
          </Card>
        )}
      </DataState>
    </section>
  );
}

const BUCKETS = ["current", "0-30", "31-60", "61-90", "90+"];

function AgingReport(props: { kind: "ar" | "ap" }) {
  const { data, error, reload } = useReport<Aging>(
    `/finance/reports/aging?type=${props.kind}`,
  );

  const columns: DataTableColumn<AgingItem>[] = [
    { key: "number", header: "Number", sortable: true, accessor: (i) => i.number ?? "—" },
    {
      key: "party",
      header: props.kind === "ar" ? "Customer" : "Vendor",
      sortable: true,
      accessor: (i) => <b>{i.party}</b>,
      sortValue: (i) => i.party,
    },
    {
      key: "due_date",
      header: "Due",
      sortable: true,
      accessor: (i) => new Date(i.due_date).toLocaleDateString(),
      sortValue: (i) => i.due_date,
    },
    {
      key: "days_overdue",
      header: "Days overdue",
      numeric: true,
      sortable: true,
      accessor: (i) => (i.days_overdue > 0 ? <b className={styles.owing}>{i.days_overdue}</b> : "—"),
      sortValue: (i) => i.days_overdue,
    },
    {
      key: "outstanding",
      header: "Outstanding",
      numeric: true,
      sortable: true,
      accessor: (i) => money(i.outstanding),
      sortValue: (i) => i.outstanding,
    },
  ];

  return (
    <section>
      <CardHeader
        title={`${props.kind.toUpperCase()} aging`}
        description={data ? `${money(data.total)} open` : undefined}
      />
      <DataState loading={!data && !error} error={data ? null : error} onRetry={reload}>
        {data && (
          <Stack gap={4}>
            <Grid min={168}>
              {BUCKETS.map((label) => (
                <KpiCard
                  key={label}
                  label={label === "current" ? "Not due" : `${label} days`}
                  value={money(data.buckets[label]?.total ?? 0)}
                  hint={`${data.buckets[label]?.count ?? 0} doc(s)`}
                />
              ))}
            </Grid>

            {data.items.length === 0 ? (
              <DataState isEmpty emptyTitle="Nothing outstanding">{null}</DataState>
            ) : (
              <DataTable
                data={data.items}
                columns={columns}
                getRowId={(i) => i.id}
                searchPlaceholder="Search documents…"
              />
            )}
          </Stack>
        )}
      </DataState>
    </section>
  );
}
