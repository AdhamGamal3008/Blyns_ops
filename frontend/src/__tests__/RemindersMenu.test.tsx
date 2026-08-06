// The reminders bell (formerly the dashboard SuggestionsStrip): it fetches the
// server's data-state nudges, badges the bell with the count, and opens a panel
// where each row deep-links and can be dismissed (optimistic remove + POST).
//
// The bell refreshes on every open, so the fetch mocks return a *fresh* Response
// per call — a Response body can only be read once.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RemindersMenu } from "../client/dashboard/RemindersMenu";

const { navigate } = vi.hoisted(() => ({ navigate: vi.fn() }));
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigate };
});

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

const drafts = {
  key: "finance.draft_invoices", message: "2 draft invoices are waiting to be sent.",
  cta_label: "Review drafts", target_route: "/app/finance/invoices", priority: 80,
};
const leads = {
  key: "crm.new_leads", message: "3 new leads need following up.",
  cta_label: "Work leads", target_route: "/app/crm/leads", priority: 70,
};

/** The reminders live behind the bell — open the panel to reach them. */
function openPanel() {
  fireEvent.click(screen.getByRole("button", { name: /^Reminders/ }));
}

describe("RemindersMenu", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    navigate.mockClear();
  });

  it("badges the bell and lists each reminder, with a CTA that navigates", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => okJson({ data: [drafts, leads] })));
    render(<MemoryRouter><RemindersMenu /></MemoryRouter>);

    // the pending count lands in the bell's accessible name once fetch resolves
    await screen.findByRole("button", { name: "Reminders, 2 pending" });

    openPanel();
    await waitFor(() => expect(screen.getByText(drafts.message)).toBeInTheDocument());
    expect(screen.getByText(leads.message)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Review drafts" }));
    expect(navigate).toHaveBeenCalledWith("/app/finance/invoices");
  });

  it("shows an empty state and no count when there are no reminders", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => okJson({ data: [] })));
    render(<MemoryRouter><RemindersMenu /></MemoryRouter>);

    // no pending suffix — the bell is just "Reminders"
    fireEvent.click(await screen.findByRole("button", { name: "Reminders" }));

    await waitFor(() => expect(screen.getByText(/all caught up/i)).toBeInTheDocument());
  });

  it("dismisses a reminder (POST) and drops it from the panel", async () => {
    const mock = vi.fn(async (url: string, _init?: RequestInit) => {
      const u = String(url);
      if (u.endsWith("/dismiss")) return okJson({ data: [leads] }); // server's remainder
      return okJson({ data: [drafts, leads] });
    });
    vi.stubGlobal("fetch", mock);
    render(<MemoryRouter><RemindersMenu /></MemoryRouter>);

    await screen.findByRole("button", { name: "Reminders, 2 pending" });
    openPanel();
    await waitFor(() => expect(screen.getByText(drafts.message)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: `Dismiss: ${drafts.message}` }));

    await waitFor(() => expect(screen.queryByText(drafts.message)).not.toBeInTheDocument());
    expect(screen.getByText(leads.message)).toBeInTheDocument();

    const post = mock.mock.calls.find(
      ([url, i]) => String(url).endsWith("/dismiss") && i?.method === "POST");
    expect(post).toBeTruthy();
    expect(String(post![0])).toContain(
      "/dashboard/suggestions/finance.draft_invoices/dismiss");
  });
});
