// Production Phase 2 UI (docs/PRODUCTION_MODULE_PLAN.md §2.3): the WO detail
// surfaces the status action for a qc_pending WO and the read-only pipeline
// mirror — Production links out to approve, it never hosts the approve.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WorkOrderDetail } from "../client/production/WorkOrderDetail";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

const WO = {
  data: {
    id: "w1", code: "WO-0001-01", project_id: "p1", project_code: "PRJ-0001",
    item_name: "Lobby panels", bom_lines: [], qty: { ordered: 42, done: 42 },
    station_route: [], current_station_id: null, station_name: null,
    due_date: null, status: "qc_pending", revision_conflict: false,
  },
};

const ROLLUP = {
  data: {
    project_id: "p1", project_code: "PRJ-0001",
    sections: { production: 100, quality_control: 0 },
    release_checklist: ["production", "quality_control", "packing_protection", "delivery_planning"],
    checklist_done: ["production"], stage_order: 6, stage_status: "in_progress",
    releasable: false,
  },
};

function stubFetch() {
  const mock = vi.fn(async (url: string, _init?: RequestInit) => {
    const u = String(url);
    if (u.includes("/production/work-orders/w1/qc")) {
      return okJson({ data: { ...WO.data, status: "passed" } });
    }
    if (/\/production\/work-orders\/w1$/.test(u)) return okJson(WO);
    if (u.includes("/production/projects/p1/rollup")) return okJson(ROLLUP);
    return okJson({ data: {} });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

function renderDetail() {
  return render(
    <MemoryRouter>
      <WorkOrderDetail woId="w1" canWrite canManage onClose={() => {}} onChanged={() => {}} />
    </MemoryRouter>,
  );
}

describe("WorkOrderDetail", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("shows the QC action and the read-only pipeline mirror", async () => {
    stubFetch();
    renderDetail();
    await waitFor(() => expect(screen.getByText("Lobby panels")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Pass QC" })).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Approve in pipeline/ });
    expect(link).toHaveAttribute("href", "/app/projects/p1");
  });

  it("passes QC through the API", async () => {
    const mock = stubFetch();
    renderDetail();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Pass QC" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Pass QC" }));
    await waitFor(() => {
      const call = mock.mock.calls.find(([u, init]) =>
        String(u).includes("/work-orders/w1/qc") && init?.method === "POST");
      expect(call).toBeTruthy();
      expect(JSON.parse(String(call![1]!.body)).result).toBe("pass");
    });
  });

  it("packs a passed work order through the API", async () => {
    const passed = { ...WO.data, status: "passed" };
    const mock = vi.fn(async (url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes("/production/work-orders/w1/pack") && init?.method === "POST") {
        return okJson({ data: { ...passed, status: "packed" } });
      }
      if (/\/production\/work-orders\/w1$/.test(u)) return okJson({ data: passed });
      if (u.includes("/production/projects/p1/rollup")) return okJson(ROLLUP);
      return okJson({ data: {} });
    });
    vi.stubGlobal("fetch", mock);
    render(
      <MemoryRouter>
        <WorkOrderDetail woId="w1" canWrite canManage onClose={() => {}} onChanged={() => {}} />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Pack/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Pack/ }));
    await waitFor(() => {
      const call = mock.mock.calls.find(([u, init]) =>
        String(u).includes("/work-orders/w1/pack") && init?.method === "POST");
      expect(call).toBeTruthy();
    });
  });
});
