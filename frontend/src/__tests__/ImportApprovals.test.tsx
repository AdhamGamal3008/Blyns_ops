// Per-module CSV import approvals inbox (docs/modules/SETTINGS.md §1.3). The
// properties that matter: it appears only for someone with the grants and only
// when there is something to act on, and Approve/Reject reach the server.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ImportApprovals } from "../shared/csv/ImportApprovals";
import type { ClientMe } from "../shared/types";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

function me(csv_access: ClientMe["role"]["csv_access"]): ClientMe {
  return {
    id: "u1", email: "a@acme.test", name: "Ann", must_reset_password: false,
    company: { slug: "acme", name: "Acme", enabled_modules: ["crm"] },
    role: { id: "r1", name: "Role", permissions: { crm: 2 }, csv_access },
  };
}

const APPROVER = me({ export: [], import: [], approve_import: ["crm:accounts"] });
const REQUESTER = me({ export: [], import: ["crm:accounts"], approve_import: [] });
const NO_GRANTS = me({ export: [], import: [], approve_import: [] });

const pending = {
  id: "req1", module: "crm", entity: "accounts", status: "pending",
  filename: "acc.csv", requested_by: "u2", requested_by_name: "Bob",
  requested_at: new Date().toISOString(),
  preview: { rows: 3, created: 2, updated: 0, failed: 0 },
};

/** Fresh Response per call (a shared one's body can only be read once), routed
 *  by URL: the inbox, the caller's own requests, and the approve/reject posts. */
function stubFetch(opts: { inbox?: unknown[]; mine?: unknown[] } = {}) {
  const mock = vi.fn(async (url: string, init?: RequestInit) => {
    const u = String(url);
    if (init?.method === "POST") return okJson({ data: { created: 2, updated: 0, failed: 0 } });
    if (u.includes("mine=true")) return okJson({ data: opts.mine ?? [] });
    if (u.includes("/import-requests")) return okJson({ data: opts.inbox ?? [] });
    return okJson({ data: [] });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

describe("ImportApprovals", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("renders nothing for a user with no CSV grants", () => {
    stubFetch();
    const { container } = render(<ImportApprovals me={NO_GRANTS} module="crm" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a pending request to an approver and approves it", async () => {
    const mock = stubFetch({ inbox: [pending] });
    render(<ImportApprovals me={APPROVER} module="crm" />);

    // the staged file, who staged it, and the preview counts
    expect(await screen.findByText("acc.csv")).toBeInTheDocument();
    expect(screen.getByText(/Bob/)).toBeInTheDocument();
    expect(screen.getByText("2 to create")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() =>
      expect(screen.getByText(/Approved acc\.csv/)).toBeInTheDocument());
    const approve = mock.mock.calls.find(
      ([url, init]) =>
        String(url).includes("/crm/import-requests/req1/approve") &&
        init?.method === "POST",
    );
    expect(approve).toBeTruthy();
  });

  it("shows a plain importer only their own requests", async () => {
    const mine = { ...pending, status: "rejected", reject_reason: "Wrong codes" };
    const mock = stubFetch({ mine: [mine] });
    render(<ImportApprovals me={REQUESTER} module="crm" />);

    expect(await screen.findByText("My requests")).toBeInTheDocument();
    expect(screen.getByText("Rejected")).toBeInTheDocument();
    expect(screen.getByText(/Wrong codes/)).toBeInTheDocument();
    // a plain importer never sees the approver inbox
    expect(screen.queryByText(/Pending approval/)).not.toBeInTheDocument();
    // and only ever fetches their own requests, never the inbox
    expect(mock.mock.calls.every(([url]) => String(url).includes("mine=true"))).toBe(true);
  });
});
