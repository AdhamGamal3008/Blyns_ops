// CRM Analytics tab (docs/PROJECT_ANALYTICS_PLAN.md §6-D): KPI tiles always, and
// each chart block only if present and non-empty. READ shows the charts; a VIEW
// payload (kpis only) shows just the headline row.

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CrmAnalytics } from "../client/crm/CrmAnalytics";
import type { CrmAnalytics as CrmData } from "../shared/types";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

const KPIS: CrmData["kpis"] = {
  open_deals: 3, pipeline_value: 6000, pipeline_weighted: 3300,
  win_rate: 50, open_leads: 3, customers: 2,
};

const FULL: CrmData = {
  kpis: KPIS,
  pipeline_by_stage: [
    { stage: "new", label: "New", count: 1, amount: 1000 },
    { stage: "qualified", label: "Qualified", count: 1, amount: 2000 },
  ],
  lead_status: [{ status: "new", label: "New", count: 2 }],
  lead_sources: [{ source: "website", count: 3 }],
  top_deals: [{ title: "Charlie", amount: 3000, stage: "proposal" }],
  inflow: [{ month: "2026-08", leads: 5, deals: 5 }],
};

function stub(payload: CrmData) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) =>
    String(url).includes("/crm/analytics") ? okJson({ data: payload }) : okJson({ data: {} }),
  ));
}

beforeEach(() => vi.restoreAllMocks());

describe("CrmAnalytics", () => {
  it("renders the KPI row and every chart at the READ tier", async () => {
    stub(FULL);
    render(<CrmAnalytics />);

    expect(await screen.findByText("Open deals")).toBeInTheDocument();
    expect(screen.getByText("Pipeline value")).toBeInTheDocument();
    expect(screen.getByText("Win rate")).toBeInTheDocument();
    expect(screen.getByText("Customers")).toBeInTheDocument();

    expect(screen.getByText("Open pipeline by stage")).toBeInTheDocument();
    expect(screen.getByText("Leads by status")).toBeInTheDocument();
    expect(screen.getByText("Lead sources")).toBeInTheDocument();
    expect(screen.getByText("Top open deals")).toBeInTheDocument();
    expect(screen.getByText("New leads vs deals — last 6 months")).toBeInTheDocument();
    expect(screen.getByText("New deals")).toBeInTheDocument(); // legend label
  });

  it("shows only the KPI row at the VIEW tier", async () => {
    stub({ kpis: KPIS });
    render(<CrmAnalytics />);

    expect(await screen.findByText("Open deals")).toBeInTheDocument();
    expect(screen.queryByText("Open pipeline by stage")).not.toBeInTheDocument();
    expect(screen.queryByText("New leads vs deals — last 6 months")).not.toBeInTheDocument();
  });

  it("hides a chart whose block is present but empty", async () => {
    stub({
      kpis: KPIS,
      pipeline_by_stage: [{ stage: "new", label: "New", count: 0, amount: 0 }],
      lead_status: [],
      lead_sources: [],
      top_deals: [],
      inflow: [{ month: "2026-08", leads: 0, deals: 0 }],
    });
    render(<CrmAnalytics />);

    expect(await screen.findByText("Open deals")).toBeInTheDocument();
    expect(screen.queryByText("Open pipeline by stage")).not.toBeInTheDocument();
    expect(screen.queryByText("Lead sources")).not.toBeInTheDocument();
  });
});
