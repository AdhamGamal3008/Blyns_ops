// Projects Analytics tab (docs/PROJECT_ANALYTICS_PLAN.md Phase C): the component
// renders whatever the server returns — KPI tiles always, and each chart block
// only if present. A READ payload shows the charts; a VIEW payload (kpis only)
// shows just the headline row.

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectsAnalytics } from "../client/projects/ProjectsAnalytics";
import type { ProjectAnalytics } from "../shared/types";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

const KPIS: ProjectAnalytics["kpis"] = {
  active: 5, on_hold_blocked: 2, overdue: 1, open_exceptions: 3,
  budget: { planned: 10000, actual: 8000, committed: 500, variance: -2000, variance_pct: -20 },
};

const FULL: ProjectAnalytics = {
  kpis: KPIS,
  by_stage: [
    { order: 1, key: "s1", label: "Initiation", count: 2 },
    { order: 3, key: "s3", label: "Survey", count: 3 },
  ],
  time_in_stage: [{ order: 3, key: "s3", label: "Survey", avg_days: 12, count: 3 }],
  budget: {
    portfolio: { planned: 10000, actual: 8000, committed: 500 },
    top_projects: [{ code: "PRJ-A", name: "Alpha", planned: 5000, actual: 4000 }],
    cost_by_type: [
      { cost_type: "labor", amount: 3000 },
      { cost_type: "material", amount: 2000 },
    ],
  },
  exceptions: [{ type: "ncr", open: 2, in_progress: 1, total: 3 }],
  throughput: [{ month: "2026-08", started: 4, completed: 1 }],
};

function stubAnalytics(payload: ProjectAnalytics) {
  const mock = vi.fn(async (url: string) => {
    if (String(url).includes("/projects/analytics")) return okJson({ data: payload });
    return okJson({ data: {} });
  });
  vi.stubGlobal("fetch", mock);
}

beforeEach(() => vi.restoreAllMocks());

describe("ProjectsAnalytics", () => {
  it("renders the KPI row and every chart at the READ tier", async () => {
    stubAnalytics(FULL);
    render(<ProjectsAnalytics />);

    // KPI tiles (present at VIEW+).
    expect(await screen.findByText("Active")).toBeInTheDocument();
    expect(screen.getByText("On hold / blocked")).toBeInTheDocument();
    expect(screen.getByText("Overdue")).toBeInTheDocument();
    expect(screen.getByText("Budget variance")).toBeInTheDocument();

    // One chart card per block, with legends for the multi-series ones.
    expect(screen.getByText("Active projects by stage")).toBeInTheDocument();
    expect(screen.getByText("Average days in current stage")).toBeInTheDocument();
    expect(screen.getByText("Planned vs actual — top projects")).toBeInTheDocument();
    expect(screen.getByText("Cost by type")).toBeInTheDocument();
    expect(screen.getByText("Open exceptions by type")).toBeInTheDocument();
    expect(screen.getByText("Throughput — last 6 months")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument(); // a legend label
  });

  it("shows only the KPI row at the VIEW tier (no chart blocks)", async () => {
    stubAnalytics({ kpis: KPIS }); // server omitted every chart block
    render(<ProjectsAnalytics />);

    expect(await screen.findByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Open exceptions")).toBeInTheDocument();
    // No chart cards rendered.
    expect(screen.queryByText("Active projects by stage")).not.toBeInTheDocument();
    expect(screen.queryByText("Throughput — last 6 months")).not.toBeInTheDocument();
  });

  it("hides a chart whose block is present but empty", async () => {
    // READ tier, but a brand-new tenant: blocks present, no data to plot.
    stubAnalytics({
      kpis: KPIS,
      by_stage: [{ order: 1, key: "s1", label: "Initiation", count: 0 }],
      time_in_stage: [],
      budget: { portfolio: { planned: 0, actual: 0, committed: 0 }, top_projects: [], cost_by_type: [] },
      exceptions: [],
      throughput: [{ month: "2026-08", started: 0, completed: 0 }],
    });
    render(<ProjectsAnalytics />);

    expect(await screen.findByText("Active")).toBeInTheDocument();
    expect(screen.queryByText("Active projects by stage")).not.toBeInTheDocument();
    expect(screen.queryByText("Cost by type")).not.toBeInTheDocument();
  });
});
