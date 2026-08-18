// Dashboard quick actions deep-link into a specific module tab and open its
// create form (docs/QUICK_ACTIONS_PERSONALIZATION_PLAN.md — Phase 0). Each page
// derives the active tab and the "open new" flag from the URL, so a shortcut
// like /app/finance/bills/new must land on Bills with the New-bill form open —
// not on the module's hardcoded default tab.

import { render, screen, waitFor } from "@testing-library/react";
import { type ReactNode } from "react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CrmPage } from "../client/crm/CrmPage";
import { FinancePage } from "../client/finance/FinancePage";
import { InventoryPage } from "../client/inventory/InventoryPage";
import { ProjectsPage } from "../client/projects/ProjectsPage";
import type { ClientMe } from "../shared/types";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

// The section that mounts fetches its list on mount; resolve everything to a
// benign empty shape (the pipeline needs its object shape or the board throws).
// The tab selection and open modal we assert on don't depend on the data.
function stubFetch() {
  const mock = vi.fn(async (url: string) => {
    if (String(url).includes("/crm/pipeline")) {
      return okJson({
        data: { pipeline: "default", name: "Default", stages: [], open_value: 0 },
      });
    }
    return okJson({ data: [] });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

// WRITE on every module so each page renders its create controls; no csv_access,
// so the ImportApprovals card stays out of the way.
const ME: ClientMe = {
  id: "u1", email: "o@acme.com", name: "Owner", must_reset_password: false,
  company: {
    slug: "acme", name: "Acme",
    enabled_modules: ["crm", "finance", "inventory", "projects"],
  },
  role: {
    id: "r1", name: "Owner",
    permissions: { crm: 3, finance: 3, inventory: 3, projects: 3 } as never,
  },
};

function renderAt(path: string, page: ReactNode) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<Outlet context={ME} />}>
          <Route path="/app/*" element={page} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("quick-action deep links", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  // The open dialog aria-hides the page behind it, so the tab drops out of the
  // accessible tree; `hidden: true` lets us still assert the tab underneath is
  // the selected one (the modal sits on top, which is the intended UX).
  const activeTab = (name: string) =>
    screen.getByRole("tab", { name, selected: true, hidden: true });

  it("New Deal lands on the Pipeline tab with the deal form open", async () => {
    stubFetch();
    renderAt("/app/crm/deals/new", <CrmPage />);
    // "Create deal" is the modal's submit — the header button reads "New deal".
    await waitFor(() =>
      expect(screen.getByText("Create deal")).toBeInTheDocument());
    expect(activeTab("Pipeline")).toBeInTheDocument();
  });

  it("New Contact lands on the Contacts tab with the contact form open", async () => {
    stubFetch();
    renderAt("/app/crm/contacts/new", <CrmPage />);
    await waitFor(() =>
      expect(screen.getByText("Create contact")).toBeInTheDocument());
    expect(activeTab("Contacts")).toBeInTheDocument();
  });

  it("New Bill lands on the Bills tab with the bill form open", async () => {
    stubFetch();
    renderAt("/app/finance/bills/new", <FinancePage />);
    await waitFor(() =>
      expect(screen.getByText("Save draft")).toBeInTheDocument());
    expect(activeTab("Bills")).toBeInTheDocument();
  });

  it("New Product lands on the Products tab with the product form open", async () => {
    stubFetch();
    renderAt("/app/inventory/products/new", <InventoryPage />);
    await waitFor(() =>
      expect(screen.getByText("Create product")).toBeInTheDocument());
    expect(activeTab("Products")).toBeInTheDocument();
  });

  it("a bare module route keeps the default tab and opens no form", async () => {
    stubFetch();
    renderAt("/app/crm", <CrmPage />);
    await waitFor(() =>
      expect(
        screen.getByRole("tab", { name: "Pipeline", selected: true }),
      ).toBeInTheDocument());
    // the deal form must not spring open just because pipeline is the default tab
    expect(screen.queryByText("Create deal")).not.toBeInTheDocument();
  });
  // Projects was the one module that did NOT honour this contract: /app/projects/new
  // matched the projects/:id route with id="new", so the dashboard's "Create a
  // project" shortcut opened a DETAIL page for a project that does not exist.
  it("Create a project opens the create form, not a project detail page", async () => {
    stubFetch();
    renderAt("/app/projects/new", <ProjectsPage />);
    // "Create project" is the modal's submit; the header button reads "New project".
    await waitFor(() =>
      expect(screen.getByText("Create project")).toBeInTheDocument());
  });

  it("the plain projects route does not open the create form", async () => {
    stubFetch();
    renderAt("/app/projects", <ProjectsPage />);
    await waitFor(() =>
      expect(screen.getAllByText("New project").length).toBeGreaterThan(0));
    expect(screen.queryByText("Create project")).not.toBeInTheDocument();
  });
});
