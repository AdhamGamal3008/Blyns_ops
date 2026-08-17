// Project detail for a concurrent project (docs/CONCURRENT_WORKFLOW_PLAN.md Phase 3):
// the header reflects the parallel shape — a "Concurrent" badge and a count of
// stages complete / in progress — instead of a single "Stage X of N" position.
// A sequential project keeps the linear header.

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectDetail } from "../client/projects/ProjectDetail";
import type { ClientMe } from "../shared/types";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

function me(): ClientMe {
  return {
    id: "u1", email: "o@acme.com", name: "Owner", must_reset_password: false,
    company: { slug: "acme", name: "Acme", enabled_modules: ["projects"] },
    role: { id: "r1", name: "Owner", permissions: { projects: 3 } as never },
  };
}

const NOW = "2026-08-14T00:00:00Z";

function stages(workflow: "sequential" | "concurrent") {
  // stage 1 approved; 2-8 open (concurrent) or only 2 open (sequential); 9 pending
  const mid = (order: number, open: boolean) => ({
    order, key: `s${order}`, name: `Stage ${order}`,
    status: open ? "in_progress" : "pending",
    entered_at: open ? NOW : null, recovery_loops: 0, blocking_reason: null,
  });
  return [
    { order: 1, key: "project_initiation", name: "Project Initiation",
      status: "approved", entered_at: NOW, recovery_loops: 0, blocking_reason: null },
    ...[2, 3, 4, 5, 6, 7, 8].map((o) => mid(o, workflow === "concurrent" || o === 2)),
    { order: 9, key: "final_inspection_handover", name: "Handover",
      status: "pending", entered_at: null, recovery_loops: 0, blocking_reason: null },
  ];
}

function stubFetch(
  workflow: "sequential" | "concurrent",
  configuration: { name: string | null; version: number | null } = {
    name: "Standard", version: 1,
  },
) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const u = String(url);
    if (u.includes("/timeline")) {
      return okJson({ data: {
        project_id: "p1", code: "PRJ-0001", workflow_type: workflow,
        configuration_id: configuration.name ? "c1" : null,
        config_version: configuration.version,
        configuration_name: configuration.name,
        current_stage_order: 2, milestones: [], stages: stages(workflow),
      } });
    }
    if (u.includes("/config/approver-roles")) return okJson({ data: [] });
    if (u.includes("/config/gates")) return okJson({ data: [] });
    if (/\/stages\/\d+$/.test(u)) {
      return okJson({ data: {
        definition: { order: 2, key: "s2", name: "Stage 2", entry_gates: [],
          automated_tasks: [], quality_gates: [], approver_role: null, co_approver_roles: [] },
        instance: { id: "si2", status: "in_progress", documents_supplied: [],
          waiting_on: [], blocked_by: [], task_results: [], recovery_loops: 0, blocking_reason: null },
        evaluation: { waiting_on: [], blocked_by: [], gate_failures: [], severe: false, ready: false },
        approval: null, gate_results: [],
      } });
    }
    if (/\/projects\/p1$/.test(u)) {
      return okJson({ data: {
        id: "p1", code: "PRJ-0001", name: "Parallel build", workflow_type: workflow,
        current_stage_order: 2, current_stage_key: "s2", status: "active",
        budget: { planned: 1000, committed: 0, actual: 0, currency: "USD" },
      } });
    }
    return okJson({ data: {} });
  }));
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={["/app/projects/p1"]}>
      <Routes>
        <Route element={<Outlet context={me()} />}>
          <Route path="/app/projects/:id" element={<ProjectDetail />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProjectDetail — concurrent pipeline", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("shows the Concurrent badge and a parallel stage count", async () => {
    stubFetch("concurrent");
    renderDetail();
    // 1 approved of 9; stages 2-8 in progress = 7
    expect(await screen.findByText(/1 of 9 stages complete · 7 in progress/))
      .toBeInTheDocument();
    expect(screen.getByText("Concurrent")).toBeInTheDocument();
    // the parallel stages are in the rail to open (Stage 8 is rail-only — the tab
    // trigger reads "Stage 2", the lowest active)
    expect(screen.getByText("Stage 8")).toBeInTheDocument();
    expect(screen.getAllByText("Stage 2").length).toBeGreaterThan(0);
  });

  it("keeps the linear header for a sequential project", async () => {
    stubFetch("sequential");
    renderDetail();
    await waitFor(() =>
      expect(screen.getByText(/Stage 2 of 9/)).toBeInTheDocument());
    expect(screen.queryByText("Concurrent")).not.toBeInTheDocument();
  });

  // --- the pinned configuration (PROJECT_CONFIGURATIONS_PLAN.md Phase 4) ------

  it("names the configuration VERSION the project is pinned to", async () => {
    // Two projects on the same configuration can be running different versions,
    // so the version belongs in the header alongside the name, not in a footnote.
    stubFetch("sequential", { name: "Flooring — ASTM", version: 2 });
    renderDetail();
    expect(await screen.findByText("Flooring — ASTM v2")).toBeInTheDocument();
  });

  it("shows no configuration badge on an un-migrated workspace", async () => {
    // A project created before v4 carries no pin; the header simply omits it (G-1).
    stubFetch("sequential", { name: null, version: null });
    renderDetail();
    await waitFor(() =>
      expect(screen.getByText(/Stage 2 of 9/)).toBeInTheDocument());
    expect(screen.queryByText(/ v\d+$/)).not.toBeInTheDocument();
  });
});
