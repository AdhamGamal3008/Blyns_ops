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
    render(<StagePanel projectId="p1" order={1} canWrite canApprove canWaive={false} onChanged={() => {}} />);

    await waitFor(() =>
      expect(screen.getByText(/Lead Conversion & Project Creation/)).toBeInTheDocument());
    // the supplied entry document is reflected
    expect(screen.getByText("supplied")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Submit for approval"));
    await waitFor(() => expect(postCall(mock, "/stages/1/submit")).toBeTruthy());
  });

  it("offers Approve/Reject only when the stage awaits a decision", async () => {
    stubFetch("pending_approval");
    render(<StagePanel projectId="p1" order={1} canWrite canApprove canWaive={false} onChanged={() => {}} />);

    await waitFor(() => expect(screen.getByText("Approve")).toBeInTheDocument());
    expect(screen.getByText("Reject")).toBeInTheDocument();
    expect(screen.queryByText("Submit for approval")).not.toBeInTheDocument();
  });

  it("hides approve controls from a user who cannot approve", async () => {
    stubFetch("pending_approval");
    render(<StagePanel projectId="p1" order={1} canWrite={false} canApprove={false}
      canWaive={false} onChanged={() => {}} />);

    await waitFor(() =>
      expect(screen.getByText(/Lead Conversion/)).toBeInTheDocument());
    expect(screen.queryByText("Approve")).not.toBeInTheDocument();
    expect(screen.queryByText("Submit for approval")).not.toBeInTheDocument();
  });

  it("offers a supply control for a foundational-phase gate (regression: Stage 14)", async () => {
    // A `dependency` entry gate whose `depends_on` is a PHASE (not a prior
    // stage) is cleared by supplying its key as a document; the engine surfaces
    // it as `phase:<key>` in waiting_on. Before the fix the UI rendered no
    // control for it, so the stage was stuck in `waiting` forever.
    const detail = {
      data: {
        definition: {
          order: 14, key: "installation", name: "Installation",
          entry_gates: [
            { key: "site_readiness_cleared", type: "dependency", blocking: true, depends_on: "site_readiness" },
            { key: "acclimation_complete", type: "dependency", blocking: true, depends_on: "core_material_acclimation" },
          ],
          automated_tasks: [], quality_gates: [],
          approver_role: "site_supervisor", co_approver_roles: [],
        },
        instance: {
          id: "si14", status: "waiting", documents_supplied: [],
          waiting_on: [], blocked_by: [], task_results: [],
          recovery_loops: 0, blocking_reason: null,
        },
        evaluation: {
          waiting_on: ["phase:core_material_acclimation"], blocked_by: [],
          gate_failures: [], severe: false, ready: false,
        },
        approval: null, gate_results: [],
      },
    };
    const mock = vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/config/gates")) return okJson({ data: [] });
      if (u.includes("/stages/14")) return okJson(detail);
      return okJson({ data: {} });
    });
    vi.stubGlobal("fetch", mock);

    render(<StagePanel projectId="p1" order={14} canWrite canApprove canWaive={false} onChanged={() => {}} />);

    // the phase gate is offered under Entry requirements with a supply control…
    await waitFor(() => expect(screen.getByText("Acclimation complete")).toBeInTheDocument());
    expect(screen.getByText(/phase · Core material acclimation/)).toBeInTheDocument();
    // …while the stage→stage dependency gets NO manual button (it clears on approval)
    expect(screen.queryByText("Site readiness cleared")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Mark supplied"));
    await waitFor(() =>
      expect(postCall(mock, "/stages/14/documents/acclimation_complete")).toBeTruthy());
  });

  it("requires evidence on a document gate — no bare mark-supplied", async () => {
    const detail = {
      data: {
        definition: {
          order: 1, key: "lead_conversion", name: "Lead Conversion",
          entry_gates: [{ key: "contract_signed", type: "document", blocking: true }],
          automated_tasks: [], quality_gates: [],
          approver_role: "project_director", co_approver_roles: [],
        },
        instance: {
          id: "si1", status: "waiting", documents_supplied: [], document_refs: [],
          waiting_on: [], blocked_by: [], task_results: [],
          recovery_loops: 0, blocking_reason: null,
        },
        evaluation: {
          waiting_on: ["doc:contract_signed"], blocked_by: [],
          gate_failures: [], severe: false, ready: false,
        },
        approval: null, gate_results: [],
      },
    };
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/config/gates")) return okJson({ data: [] });
      if (u.includes("/stages/1")) return okJson(detail);
      return okJson({ data: {} });
    }));

    render(<StagePanel projectId="p1" order={1} canWrite canApprove canWaive={false} onChanged={() => {}} />);
    await waitFor(() => expect(screen.getByText("Contract signed")).toBeInTheDocument());
    // the only way to satisfy it is to attach a file or a URL
    expect(screen.getByText("Attach")).toBeInTheDocument();
    expect(screen.queryByText("Mark supplied")).not.toBeInTheDocument();
  });

  it("lets a non-writing approver open the evidence attached to a gate", async () => {
    const detail = {
      data: {
        definition: {
          order: 1, key: "lead_conversion", name: "Lead Conversion",
          entry_gates: [{ key: "contract_signed", type: "document", blocking: true }],
          automated_tasks: [], quality_gates: [],
          approver_role: "project_director", co_approver_roles: [],
        },
        instance: {
          id: "si1", status: "in_progress", documents_supplied: ["contract_signed"],
          document_refs: [{
            gate_key: "contract_signed", deliverable_id: "d1",
            title: "Contract PDF", version: 2, source_type: "url",
            file_ref: "https://x.example.com/contract.pdf",
            by: "u1", at: "2026-07-23T10:00:00Z",
          }],
          waiting_on: [], blocked_by: [], task_results: [],
          recovery_loops: 0, blocking_reason: null,
        },
        evaluation: { waiting_on: [], blocked_by: [], gate_failures: [], severe: false, ready: true },
        approval: null, gate_results: [],
      },
    };
    const mock = vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/config/gates")) return okJson({ data: [] });
      if (u.includes("/deliverables")) return okJson({ data: [] });
      if (u.includes("/stages/1")) return okJson(detail);
      return okJson({ data: {} });
    });
    vi.stubGlobal("fetch", mock);

    // an approver with no write access still sees — and can open — the evidence
    render(<StagePanel projectId="p1" order={1} canWrite={false} canApprove
      canWaive={false} onChanged={() => {}} />);
    await waitFor(() => expect(screen.getByText("Contract signed")).toBeInTheDocument());
    expect(screen.getByText("Contract PDF")).toHaveAttribute(
      "href", "https://x.example.com/contract.pdf");
  });

  // --- v2.0 affordances -------------------------------------------------------

  it("shows the auto-advance stage as approver-less and completes on submit", async () => {
    const detail = {
      data: {
        definition: {
          order: 2, key: "site_survey", name: "Site Survey & Technical Assessment",
          entry_gates: [], automated_tasks: [], quality_gates: [],
          approver_role: null, co_approver_roles: [], auto_advance: true,
        },
        instance: {
          id: "si2", status: "in_progress", documents_supplied: [],
          waiting_on: [], blocked_by: [], task_results: [],
          recovery_loops: 0, blocking_reason: null,
        },
        evaluation: { waiting_on: [], blocked_by: [], gate_failures: [], severe: false, ready: true },
        approval: null, gate_results: [],
      },
    };
    const mock = vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/config/gates")) return okJson({ data: [] });
      if (u.includes("/stages/2/submit"))
        return okJson({ data: { auto_advanced: true, validation: { passed: true, checks: [] } } });
      if (u.includes("/stages/2")) return okJson(detail);
      return okJson({ data: {} });
    });
    vi.stubGlobal("fetch", mock);

    render(<StagePanel projectId="p1" order={2} canWrite canApprove canWaive={false}
      onChanged={() => {}} />);
    await waitFor(() =>
      expect(screen.getByText(/Auto-advances on completion/)).toBeInTheDocument());
    // no approval step — the button completes the stage, and Approve never shows
    expect(screen.getByText("Complete stage")).toBeInTheDocument();
    expect(screen.queryByText("Submit for approval")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Complete stage"));
    await waitFor(() => expect(postCall(mock, "/stages/2/submit")).toBeTruthy());
  });

  it("offers a director-only Waive control on a blocking quality gate", async () => {
    const detail = {
      data: {
        definition: {
          order: 4, key: "measurement_verification", name: "Measurement Verification",
          entry_gates: [], automated_tasks: [],
          quality_gates: ["deviation_within_tolerance"],
          approver_role: "engineering", co_approver_roles: [],
        },
        instance: {
          id: "si4", status: "in_progress", documents_supplied: [],
          waiting_on: [], blocked_by: [], task_results: [],
          recovery_loops: 0, blocking_reason: null,
        },
        evaluation: { waiting_on: [], blocked_by: [], gate_failures: [], severe: false, ready: false },
        approval: null, gate_results: [],
      },
    };
    const gates = [{ key: "deviation_within_tolerance", type: "measurement", blocking: true }];
    const mock = vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/config/gates")) return okJson({ data: gates });
      if (u.includes("/gates/deviation_within_tolerance/waive")) return okJson({ data: {} });
      if (u.includes("/stages/4")) return okJson(detail);
      return okJson({ data: {} });
    });
    vi.stubGlobal("fetch", mock);

    // a non-director sees no Waive control
    const { unmount } = render(<StagePanel projectId="p1" order={4} canWrite canApprove
      canWaive={false} onChanged={() => {}} />);
    await waitFor(() =>
      expect(screen.getByText(/Measurement Verification/)).toBeInTheDocument());
    expect(screen.queryByText("Waive")).not.toBeInTheDocument();
    unmount();

    // a director does — clicking waives with a reason
    render(<StagePanel projectId="p1" order={4} canWrite canApprove canWaive
      onChanged={() => {}} />);
    await waitFor(() => expect(screen.getByText("Waive")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Waive"));
    await waitFor(() =>
      expect(document.querySelector('input[placeholder^="Why this hard gate"]')).toBeTruthy());
    const reason = document.querySelector('input[placeholder^="Why this hard gate"]')!;
    fireEvent.change(reason, { target: { value: "As-built within intent" } });
    fireEvent.click(screen.getByText("Waive gate"));
    await waitFor(() =>
      expect(postCall(mock, "/gates/deviation_within_tolerance/waive")).toBeTruthy());
  });

  it("renders a waived gate as waived, not failed", async () => {
    const detail = {
      data: {
        definition: {
          order: 4, key: "measurement_verification", name: "Measurement Verification",
          entry_gates: [], automated_tasks: [],
          quality_gates: ["deviation_within_tolerance"],
          approver_role: "engineering", co_approver_roles: [],
        },
        instance: {
          id: "si4", status: "in_progress", documents_supplied: [],
          waiting_on: [], blocked_by: [], task_results: [],
          recovery_loops: 0, blocking_reason: null,
        },
        evaluation: { waiting_on: [], blocked_by: [], gate_failures: [], severe: false, ready: true },
        approval: null,
        gate_results: [{
          id: "g1", gate_key: "deviation_within_tolerance", type: "measurement",
          passed: true, severe: false, waived: true, reason: "Signed off",
          explanation: "", captured_at: "2026-07-30T00:00:00Z",
        }],
      },
    };
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/config/gates")) return okJson({ data: [] });
      if (u.includes("/stages/4")) return okJson(detail);
      return okJson({ data: {} });
    }));

    render(<StagePanel projectId="p1" order={4} canWrite canApprove canWaive
      onChanged={() => {}} />);
    await waitFor(() => expect(screen.getByText("waived")).toBeInTheDocument());
  });

  it("shows the Stage 6 release checklist and marks a section complete", async () => {
    const detail = {
      data: {
        definition: {
          order: 6, key: "factory_release", name: "Factory Release",
          entry_gates: [], automated_tasks: [], quality_gates: [],
          approver_role: "production_manager", co_approver_roles: [],
          release_checklist: ["production", "quality_control", "packing_protection", "delivery_planning"],
        },
        instance: {
          id: "si6", status: "in_progress", documents_supplied: [],
          checklist_done: ["production"],
          waiting_on: [], blocked_by: [], task_results: [],
          recovery_loops: 0, blocking_reason: null,
        },
        evaluation: { waiting_on: [], blocked_by: [], gate_failures: [], severe: false, ready: false },
        approval: null, gate_results: [],
      },
    };
    const mock = vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/config/gates")) return okJson({ data: [] });
      if (u.includes("/checklist/")) return okJson({ data: {} });
      if (u.includes("/stages/6")) return okJson(detail);
      return okJson({ data: {} });
    });
    vi.stubGlobal("fetch", mock);

    render(<StagePanel projectId="p1" order={6} canWrite canApprove canWaive={false}
      onChanged={() => {}} />);
    await waitFor(() => expect(screen.getByText("Release checklist")).toBeInTheDocument());
    // one section already complete, the rest pending
    expect(screen.getByText("complete")).toBeInTheDocument();
    expect(screen.getAllByText("Mark complete").length).toBe(3);
    fireEvent.click(screen.getAllByText("Mark complete")[0]);
    await waitFor(() => expect(postCall(mock, "/checklist/")).toBeTruthy());
  });

  it("offers a client-acceptance control on the handover stage", async () => {
    const detail = {
      data: {
        definition: {
          order: 9, key: "final_inspection_handover", name: "Final Inspection & Client Handover",
          entry_gates: [], automated_tasks: [], quality_gates: [],
          approver_role: "project_director", co_approver_roles: [],
        },
        instance: {
          id: "si9", status: "in_progress", documents_supplied: [],
          waiting_on: [], blocked_by: [], task_results: [],
          recovery_loops: 0, blocking_reason: null,
        },
        evaluation: { waiting_on: [], blocked_by: [], gate_failures: [], severe: false, ready: true },
        approval: null, gate_results: [],
      },
    };
    const mock = vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/config/gates")) return okJson({ data: [] });
      if (u.includes("/client-acceptance")) return okJson({ data: {} });
      if (u.includes("/stages/9")) return okJson(detail);
      return okJson({ data: {} });
    });
    vi.stubGlobal("fetch", mock);

    render(<StagePanel projectId="p1" order={9} canWrite canApprove canWaive={false}
      onChanged={() => {}} />);
    await waitFor(() =>
      expect(screen.getByText("Record client acceptance")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Record client acceptance"));
    await waitFor(() =>
      expect(screen.getByText(/lets the handover proceed/)).toBeInTheDocument());
    const note = document.querySelector('input[placeholder^="e.g. Client accepts"]')!;
    fireEvent.change(note, { target: { value: "Client accepts the reveal" } });
    fireEvent.click(screen.getByText("Record acceptance"));
    await waitFor(() => expect(postCall(mock, "/client-acceptance")).toBeTruthy());
  });
});
