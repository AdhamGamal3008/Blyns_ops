// Admin Companies page: the module list must offer every known module (incl.
// Production), and modules must be editable on an existing tenant — a company
// onboarded before a module existed can be given it without a re-onboard.

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CompaniesPage } from "../admin/CompaniesPage";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

const COMPANIES = {
  data: [
    {
      id: "c1", name: "Acme", slug: "acme", status: "active",
      seat_limit: 25, seats_used: 3,
      // onboarded before Production existed — no "production" here
      enabled_modules: ["dashboard", "settings", "projects", "crm", "inventory", "finance"],
    },
  ],
  meta: { total: 1 },
};

function stubFetch() {
  const mock = vi.fn(async (url: string, _init?: RequestInit) => {
    if (String(url).includes("/admin/companies")) return okJson(COMPANIES);
    return okJson({ data: [] });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

function renderPage() {
  return render(<MemoryRouter><CompaniesPage /></MemoryRouter>);
}

describe("CompaniesPage modules", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("enables Production on an existing tenant via the Modules editor", async () => {
    const mock = stubFetch();
    renderPage();
    await waitFor(() => expect(screen.getByText("Acme")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Modules" }));

    // the editor offers Production (missing from this tenant) unchecked
    const dialog = await screen.findByRole("dialog");
    const production = within(dialog).getByRole("checkbox", { name: "production" });
    expect(production).not.toBeChecked();
    fireEvent.click(production);

    fireEvent.click(within(dialog).getByRole("button", { name: "Save modules" }));

    await waitFor(() => {
      const patch = mock.mock.calls.find(
        ([u, init]) =>
          String(u).includes("/admin/companies/c1") &&
          (init as RequestInit)?.method === "PATCH",
      );
      expect(patch).toBeTruthy();
      expect(JSON.parse(String((patch![1] as RequestInit).body)).enabled_modules)
        .toContain("production");
    });
  });
});
