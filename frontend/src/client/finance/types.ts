import type { BadgeTone } from "../../shared/ui";

// Shared shapes for the Finance section (docs/modules/FINANCE.md §1).

export interface Account {
  id: string;
  code: string;
  name: string;
  type: "asset" | "liability" | "equity" | "income" | "expense";
  is_active: boolean;
  currency?: string;
}

export interface DocLine {
  description: string;
  qty: number;
  unit_price: number;
  tax_rate: number;
  amount: number;
  tax_amount?: number;
  product_id?: string | null;
}

export interface Invoice {
  id: string;
  number: string | null;
  customer_ref: { crm_account_id?: string | null; name: string };
  issue_date: string;
  due_date: string;
  lines: DocLine[];
  subtotal: number;
  tax_total: number;
  total: number;
  paid_amount: number;
  status: "draft" | "sent" | "partly_paid" | "paid" | "void";
  currency: string;
  inventory_issue?: boolean;
  void_reason?: string | null;
}

export interface Bill {
  id: string;
  number: string | null;
  vendor_ref: { name: string };
  issue_date: string;
  due_date: string;
  total: number;
  paid_amount: number;
  status: string;
  currency: string;
}

export interface TrialBalanceRow {
  account_id: string;
  code: string;
  name: string;
  type: string;
  debit: number;
  credit: number;
  balance: number;
}

export interface TrialBalance {
  rows: TrialBalanceRow[];
  debit_total: number;
  credit_total: number;
  balanced: boolean;
}

export interface Pnl {
  income: (TrialBalanceRow & { amount: number })[];
  expense: (TrialBalanceRow & { amount: number })[];
  income_total: number;
  expense_total: number;
  net_profit: number;
}

export interface BalanceSheet {
  assets: TrialBalanceRow[];
  liabilities: TrialBalanceRow[];
  equity: TrialBalanceRow[];
  assets_total: number;
  liabilities_total: number;
  equity_total: number;
  retained_earnings: number;
  liabilities_and_equity_total: number;
  balanced: boolean;
}

export interface AgingItem {
  id: string;
  number: string | null;
  party: string;
  due_date: string;
  days_overdue: number;
  outstanding: number;
  bucket: string;
}

export interface Aging {
  type: string;
  buckets: Record<string, { total: number; count: number }>;
  items: AgingItem[];
  total: number;
}

export const STATUS_TONE: Record<string, BadgeTone> = {
  draft: "neutral", sent: "info", partly_paid: "warning",
  paid: "success", void: "danger",
};

export function money(n: number, currency = "USD"): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency", currency, maximumFractionDigits: 2,
  }).format(n ?? 0);
}
