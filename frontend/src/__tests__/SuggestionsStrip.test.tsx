// The dashboard "next step" strip (Phase 3): it renders the server's data-state
// suggestions, each CTA deep-links, and dismissing one removes it and POSTs to
// the dismiss endpoint.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SuggestionsStrip } from "../client/dashboard/SuggestionsStrip";

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

describe("SuggestionsStrip", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    navigate.mockClear();
  });

  it("renders nothing when there are no suggestions", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okJson({ data: [] })));
    const { container } = render(<MemoryRouter><SuggestionsStrip /></MemoryRouter>);
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("shows each suggestion and its CTA navigates", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okJson({ data: [drafts, leads] })));
    render(<MemoryRouter><SuggestionsStrip /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText(drafts.message)).toBeInTheDocument());
    expect(screen.getByText(leads.message)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Review drafts" }));
    expect(navigate).toHaveBeenCalledWith("/app/finance/invoices");
  });

  it("dismisses a suggestion (POST) and drops it from the strip", async () => {
    const mock = vi.fn(async (url: string, _init?: RequestInit) => {
      const u = String(url);
      if (u.endsWith("/dismiss")) return okJson({ data: [leads] }); // server's remainder
      return okJson({ data: [drafts, leads] });
    });
    vi.stubGlobal("fetch", mock);
    render(<MemoryRouter><SuggestionsStrip /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText(drafts.message)).toBeInTheDocument());

    // the first card is the drafts suggestion — dismiss it
    fireEvent.click(screen.getAllByRole("button", { name: "Dismiss" })[0]);

    await waitFor(() => expect(screen.queryByText(drafts.message)).not.toBeInTheDocument());
    expect(screen.getByText(leads.message)).toBeInTheDocument();

    const post = mock.mock.calls.find(
      ([url, i]) => String(url).endsWith("/dismiss") && i?.method === "POST");
    expect(post).toBeTruthy();
    expect(String(post![0])).toContain(
      "/dashboard/suggestions/finance.draft_invoices/dismiss");
  });
});
