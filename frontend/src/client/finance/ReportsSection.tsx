// Reports (§2): trial balance, P&L, balance sheet, AR/AP aging. The balance
// checks are surfaced, not hidden — a book that stops balancing should be
// visible at a glance.

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import { Badge, Card, ErrorNote, Spinner } from "../../shared/ui";
import {
  money,
  type Aging,
  type BalanceSheet,
  type Pnl,
  type TrialBalance,
} from "./types";

const REPORTS = [
  { key: "trial-balance", label: "Trial balance" },
  { key: "pnl", label: "Profit & loss" },
  { key: "balance-sheet", label: "Balance sheet" },
  { key: "ar", label: "AR aging" },
  { key: "ap", label: "AP aging" },
] as const;

export function ReportsSection() {
  const [report, setReport] = useState<string>("trial-balance");

  return (
    <>
      <div className="quick-actions" style={{ marginBottom: 16 }}>
        {REPORTS.map((r) => (
          <button key={r.key}
            className={`btn ${report === r.key ? "btn-primary" : "btn-ghost"}`}
            onClick={() => setReport(r.key)}>
            {r.label}
          </button>
        ))}
      </div>
      {report === "trial-balance" && <TrialBalanceReport />}
      {report === "pnl" && <PnlReport />}
      {report === "balance-sheet" && <BalanceSheetReport />}
      {(report === "ar" || report === "ap") && <AgingReport kind={report} />}
    </>
  );
}

function useReport<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(() => {
    api<T>(path).then((r) => setData(r.data)).catch(setError);
  }, [path]);
  useEffect(load, [load]);
  return { data, error };
}

export function TrialBalanceReport() {
  const { data, error } = useReport<TrialBalance>("/finance/reports/trial-balance");
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Spinner />;

  return (
    <Card
      title="Trial balance"
      actions={
        <Badge tone={data.balanced ? "ok" : "danger"}>
          {data.balanced ? "balanced" : "OUT OF BALANCE"}
        </Badge>
      }
    >
      <table className="table">
        <thead>
          <tr>
            <th>Code</th><th>Account</th><th>Type</th>
            <th style={{ textAlign: "right" }}>Debit</th>
            <th style={{ textAlign: "right" }}>Credit</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r) => (
            <tr key={r.account_id}>
              <td className="muted">{r.code}</td>
              <td><b>{r.name}</b></td>
              <td className="muted">{r.type}</td>
              <td style={{ textAlign: "right" }}>{r.debit ? money(r.debit) : "—"}</td>
              <td style={{ textAlign: "right" }}>{r.credit ? money(r.credit) : "—"}</td>
            </tr>
          ))}
          {data.rows.length === 0 && (
            <tr><td colSpan={5} className="muted">Nothing posted yet.</td></tr>
          )}
        </tbody>
        <tfoot>
          <tr>
            <td colSpan={3}><b>Total</b></td>
            <td style={{ textAlign: "right" }}><b>{money(data.debit_total)}</b></td>
            <td style={{ textAlign: "right" }}><b>{money(data.credit_total)}</b></td>
          </tr>
        </tfoot>
      </table>
    </Card>
  );
}

function PnlReport() {
  const { data, error } = useReport<Pnl>("/finance/reports/pnl");
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Spinner />;

  return (
    <Card title="Profit &amp; loss">
      <table className="table">
        <tbody>
          <tr><td colSpan={2}><b>Income</b></td></tr>
          {data.income.map((r) => (
            <tr key={r.account_id}>
              <td className="muted" style={{ paddingLeft: 20 }}>{r.name}</td>
              <td style={{ textAlign: "right" }}>{money(r.amount)}</td>
            </tr>
          ))}
          <tr>
            <td><b>Total income</b></td>
            <td style={{ textAlign: "right" }}><b>{money(data.income_total)}</b></td>
          </tr>
          <tr><td colSpan={2}><b>Expense</b></td></tr>
          {data.expense.map((r) => (
            <tr key={r.account_id}>
              <td className="muted" style={{ paddingLeft: 20 }}>{r.name}</td>
              <td style={{ textAlign: "right" }}>{money(r.amount)}</td>
            </tr>
          ))}
          <tr>
            <td><b>Total expense</b></td>
            <td style={{ textAlign: "right" }}><b>{money(data.expense_total)}</b></td>
          </tr>
        </tbody>
        <tfoot>
          <tr>
            <td><b>Net profit</b></td>
            <td style={{ textAlign: "right" }}>
              <b className={data.net_profit >= 0 ? "qty-in" : "qty-out"}>
                {money(data.net_profit)}
              </b>
            </td>
          </tr>
        </tfoot>
      </table>
    </Card>
  );
}

function BalanceSheetReport() {
  const { data, error } = useReport<BalanceSheet>("/finance/reports/balance-sheet");
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Spinner />;

  return (
    <Card
      title="Balance sheet"
      actions={
        <Badge tone={data.balanced ? "ok" : "danger"}>
          {data.balanced ? "balanced" : "OUT OF BALANCE"}
        </Badge>
      }
    >
      <table className="table">
        <tbody>
          <tr><td colSpan={2}><b>Assets</b></td></tr>
          {data.assets.map((r) => (
            <tr key={r.account_id}>
              <td className="muted" style={{ paddingLeft: 20 }}>{r.name}</td>
              <td style={{ textAlign: "right" }}>{money(r.balance)}</td>
            </tr>
          ))}
          <tr>
            <td><b>Total assets</b></td>
            <td style={{ textAlign: "right" }}><b>{money(data.assets_total)}</b></td>
          </tr>
          <tr><td colSpan={2}><b>Liabilities</b></td></tr>
          {data.liabilities.map((r) => (
            <tr key={r.account_id}>
              <td className="muted" style={{ paddingLeft: 20 }}>{r.name}</td>
              <td style={{ textAlign: "right" }}>{money(-r.balance)}</td>
            </tr>
          ))}
          <tr><td colSpan={2}><b>Equity</b></td></tr>
          {data.equity.map((r) => (
            <tr key={r.account_id}>
              <td className="muted" style={{ paddingLeft: 20 }}>{r.name}</td>
              <td style={{ textAlign: "right" }}>{money(-r.balance)}</td>
            </tr>
          ))}
          <tr>
            <td className="muted" style={{ paddingLeft: 20 }}>
              Retained earnings (this period)
            </td>
            <td style={{ textAlign: "right" }}>{money(data.retained_earnings)}</td>
          </tr>
        </tbody>
        <tfoot>
          <tr>
            <td><b>Liabilities + equity</b></td>
            <td style={{ textAlign: "right" }}>
              <b>{money(data.liabilities_and_equity_total)}</b>
            </td>
          </tr>
        </tfoot>
      </table>
    </Card>
  );
}

function AgingReport(props: { kind: "ar" | "ap" }) {
  const { data, error } = useReport<Aging>(
    `/finance/reports/aging?type=${props.kind}`
  );
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Spinner />;

  const labels = ["current", "0-30", "31-60", "61-90", "90+"];
  return (
    <Card title={`${props.kind.toUpperCase()} aging — ${money(data.total)} open`}>
      <div className="kpi-grid" style={{ marginBottom: 16 }}>
        {labels.map((label) => (
          <div key={label} className="card kpi">
            <div className="kpi-label">{label === "current" ? "Not due" : `${label} days`}</div>
            <div className="kpi-value" style={{ fontSize: 20 }}>
              {money(data.buckets[label]?.total ?? 0)}
            </div>
            <div className="muted" style={{ fontSize: 11 }}>
              {data.buckets[label]?.count ?? 0} doc(s)
            </div>
          </div>
        ))}
      </div>
      <table className="table">
        <thead>
          <tr>
            <th>Number</th><th>{props.kind === "ar" ? "Customer" : "Vendor"}</th>
            <th>Due</th>
            <th style={{ textAlign: "right" }}>Days overdue</th>
            <th style={{ textAlign: "right" }}>Outstanding</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((i) => (
            <tr key={i.id}>
              <td className="muted">{i.number ?? "—"}</td>
              <td><b>{i.party}</b></td>
              <td className="muted">{new Date(i.due_date).toLocaleDateString()}</td>
              <td style={{ textAlign: "right" }}>
                {i.days_overdue > 0
                  ? <b className="qty-out">{i.days_overdue}</b>
                  : <span className="muted">—</span>}
              </td>
              <td style={{ textAlign: "right" }}>{money(i.outstanding)}</td>
            </tr>
          ))}
          {data.items.length === 0 && (
            <tr><td colSpan={5} className="muted">Nothing outstanding.</td></tr>
          )}
        </tbody>
      </table>
    </Card>
  );
}
