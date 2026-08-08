// Finance Analytics tab (docs/PROJECT_ANALYTICS_PLAN.md §6-D): KPI tiles always,
// each chart block only if present and non-empty; READ shows charts, VIEW only kpis.

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FinanceAnalytics } from "../client/finance/FinanceAnalytics";
import type { FinanceAnalytics as FinData } from "../shared/types";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

const KPIS: FinData["kpis"] = {
  revenue: 6000, expenses: 1000, ar_outstanding: 2500, ap_outstanding: 400, overdue_ar: 1000,
};

const FULL: FinData = {
  kpis: KPIS,
  invoices_by_status: [
    { status: "Sent", amount: 1000, count: 1 },
    { status: "Paid", amount: 3000, count: 1 },
  ],
  bills_by_status: [{ status: "Sent", amount: 400, count: 1 }],
  ar_aging: [{ bucket: "Current", amount: 1500 }, { bucket: "1–30", amount: 1000 }],
  top_overdue: [{ number: "INV-1", outstanding: 1000, days: 10 }],
  cashflow: [{ month: "2026-08", revenue: 6000, expenses: 1000 }],
};

function stub(payload: FinData) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) =>
    String(url).includes("/finance/analytics") ? okJson({ data: payload }) : okJson({ data: {} }),
  ));
}

beforeEach(() => vi.restoreAllMocks());

describe("FinanceAnalytics", () => {
  it("renders the KPI row and every chart at the READ tier", async () => {
    stub(FULL);
    render(<FinanceAnalytics />);

    // Unique KPI labels (Revenue/Expenses also appear as legend labels).
    expect(await screen.findByText("AR outstanding")).toBeInTheDocument();
    expect(screen.getByText("AP outstanding")).toBeInTheDocument();
    expect(screen.getByText("Overdue AR")).toBeInTheDocument();
    // Revenue shows twice: the KPI tile and the cashflow legend.
    expect(screen.getAllByText("Revenue").length).toBeGreaterThanOrEqual(2);

    expect(screen.getByText("Invoices by status")).toBeInTheDocument();
    expect(screen.getByText("Bills by status")).toBeInTheDocument();
    expect(screen.getByText("AR aging")).toBeInTheDocument();
    expect(screen.getByText("Top overdue invoices")).toBeInTheDocument();
    expect(screen.getByText("Revenue vs expenses — last 6 months")).toBeInTheDocument();
  });

  it("shows only the KPI row at the VIEW tier", async () => {
    stub({ kpis: KPIS });
    render(<FinanceAnalytics />);

    expect(await screen.findByText("AR outstanding")).toBeInTheDocument();
    expect(screen.queryByText("Invoices by status")).not.toBeInTheDocument();
    expect(screen.queryByText("Revenue vs expenses — last 6 months")).not.toBeInTheDocument();
  });

  it("hides a chart whose block is present but empty", async () => {
    stub({
      kpis: KPIS,
      invoices_by_status: [{ status: "Draft", amount: 0, count: 0 }],
      bills_by_status: [],
      ar_aging: [{ bucket: "Current", amount: 0 }],
      top_overdue: [],
      cashflow: [{ month: "2026-08", revenue: 0, expenses: 0 }],
    });
    render(<FinanceAnalytics />);

    expect(await screen.findByText("AR outstanding")).toBeInTheDocument();
    expect(screen.queryByText("Invoices by status")).not.toBeInTheDocument();
    expect(screen.queryByText("Top overdue invoices")).not.toBeInTheDocument();
  });
});
