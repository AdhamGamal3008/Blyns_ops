// Production Analytics tab (docs/PRODUCTION_MODULE_PLAN.md §7 Phase 5): KPI tiles
// always, each chart block only if present and non-empty; READ shows charts,
// VIEW only kpis.

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProductionAnalytics } from "../client/production/ProductionAnalytics";
import type { ProductionAnalytics as ProdData } from "../shared/types";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

const KPIS: ProdData["kpis"] = {
  throughput: 2, on_time_pct: 50, wip: 3, hold_rate: 67,
};

const FULL: ProdData = {
  kpis: KPIS,
  by_status: [
    { status: "dispatched", count: 2 },
    { status: "queued", count: 1 },
  ],
  by_station: [{ station: "Cutting", open: 1 }],
  throughput: [{ month: "2026-08", dispatched: 2 }],
};

function stub(payload: ProdData) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) =>
    String(url).includes("/production/analytics") ? okJson({ data: payload }) : okJson({ data: {} }),
  ));
}

beforeEach(() => vi.restoreAllMocks());

describe("ProductionAnalytics", () => {
  it("renders the KPI row and every chart at the READ tier", async () => {
    stub(FULL);
    render(<ProductionAnalytics />);

    expect(await screen.findByText("Throughput (30d)")).toBeInTheDocument();
    expect(screen.getByText("On-time")).toBeInTheDocument();
    expect(screen.getByText("Work in progress")).toBeInTheDocument();
    expect(screen.getByText("Hold rate")).toBeInTheDocument();

    expect(screen.getByText("Work orders by status")).toBeInTheDocument();
    expect(screen.getByText("Open work by station")).toBeInTheDocument();
    expect(screen.getByText("Throughput — last 6 months")).toBeInTheDocument();
  });

  it("renders '—' for a null percentage KPI", async () => {
    stub({ kpis: { throughput: 0, on_time_pct: null, wip: 0, hold_rate: null } });
    render(<ProductionAnalytics />);
    expect(await screen.findByText("On-time")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
  });

  it("shows only the KPI row at the VIEW tier", async () => {
    stub({ kpis: KPIS });
    render(<ProductionAnalytics />);

    expect(await screen.findByText("Throughput (30d)")).toBeInTheDocument();
    expect(screen.queryByText("Work orders by status")).not.toBeInTheDocument();
    expect(screen.queryByText("Open work by station")).not.toBeInTheDocument();
  });

  it("hides a chart whose block is present but empty", async () => {
    stub({
      kpis: KPIS,
      by_status: [{ status: "queued", count: 0 }],
      by_station: [],
      throughput: [{ month: "2026-08", dispatched: 0 }],
    });
    render(<ProductionAnalytics />);

    expect(await screen.findByText("Throughput (30d)")).toBeInTheDocument();
    expect(screen.queryByText("Work orders by status")).not.toBeInTheDocument();
    expect(screen.queryByText("Throughput — last 6 months")).not.toBeInTheDocument();
  });
});
