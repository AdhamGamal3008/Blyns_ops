// Stage-machine control surface (docs/modules/PROJECT_MANAGEMENT.md §5): a
// stage that passed its gates offers "Submit for approval", which posts to the
// submit endpoint; a stage awaiting a decision offers Approve/Reject.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StagePanel } from "../client/projects/StagePanel";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

function stageDetail(status: string, extra: Record<string, unknown> = {}) {
  return {
    data: {
      definition: {
        order: 1, key: "lead_conversion", name: "Lead Conversion & Project Creation",
        entry_gates: [{ key: "contract_signed", type: "document", blocking: true }],
        automated_tasks: ["create_project_record"], quality_gates: [],
        approver_role: "project_director", co_approver_roles: [],
      },
      instance: {
        id: "si1", status, documents_supplied: ["contract_signed"],
        waiting_on: [], blocked_by: [],
        task_results: [{ task: "create_project_record", status: "done" }],
        recovery_loops: 0, blocking_reason: null,
      },
      evaluation: { waiting_on: [], blocked_by: [], gate_failures: [], severe: false, ready: true },
      approval: null,
      gate_results: [],
      ...extra,
    },
  };
}

function stubFetch(status: string) {
  const mock = vi.fn(async (url: string, _init?: RequestInit) => {
    const u = String(url);
    if (u.includes("/config/gates")) return okJson({ data: [] });
    if (u.includes("/stages/1/submit"))
      return okJson({ data: { validation: { passed: true, checks: [] } } });
    if (u.includes("/stages/1")) return okJson(stageDetail(status));
    return okJson({ data: {} });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

const postCall = (mock: ReturnType<typeof stubFetch>, needle: string) =>
  mock.mock.calls.find(([u, init]) => init?.method === "POST" && String(u).includes(needle));

describe("StagePanel", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("shows the stage and submits it for approval", async () => {
    const mock = stubFetch("in_progress");
    render(<StagePanel projectId="p1" order={1} canWrite canApprove onChanged={() => {}} />);

    await waitFor(() =>
      expect(screen.getByText(/Lead Conversion & Project Creation/)).toBeInTheDocument());
    // the supplied entry document is reflected
    expect(screen.getByText("supplied")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Submit for approval"));
    await waitFor(() => expect(postCall(mock, "/stages/1/submit")).toBeTruthy());
  });

  it("offers Approve/Reject only when the stage awaits a decision", async () => {
    stubFetch("pending_approval");
    render(<StagePanel projectId="p1" order={1} canWrite canApprove onChanged={() => {}} />);

    await waitFor(() => expect(screen.getByText("Approve")).toBeInTheDocument());
    expect(screen.getByText("Reject")).toBeInTheDocument();
    expect(screen.queryByText("Submit for approval")).not.toBeInTheDocument();
  });

  it("hides approve controls from a user who cannot approve", async () => {
    stubFetch("pending_approval");
    render(<StagePanel projectId="p1" order={1} canWrite={false} canApprove={false}
      onChanged={() => {}} />);

    await waitFor(() =>
      expect(screen.getByText(/Lead Conversion/)).toBeInTheDocument());
    expect(screen.queryByText("Approve")).not.toBeInTheDocument();
    expect(screen.queryByText("Submit for approval")).not.toBeInTheDocument();
  });
});
