// Project create form (docs/CONCURRENT_WORKFLOW_PLAN.md Phase 2): the New Project
// dialog offers a workflow-type picker and sends the choice. Driving a Radix Select
// open needs pointer-capture APIs jsdom lacks, so we assert the picker renders and
// the payload carries workflow_type (default 'sequential'); the concurrent value is
// accepted + persisted by the backend (test_projects_concurrent.py).

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectsPage } from "../client/projects/ProjectsPage";
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

function stubFetch() {
  const mock = vi.fn(async (url: string, init?: RequestInit) => {
    const u = String(url);
    if (u.includes("/projects/config/stages")) return okJson({ data: [] });
    if (u.includes("/crm/accounts")) return okJson({ data: [] });
    if (u.includes("/projects") && init?.method === "POST") {
      return okJson({ data: { id: "p1" } });
    }
    return okJson({ data: [] });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/app/projects"]}>
      <Routes>
        <Route element={<Outlet context={me()} />}>
          <Route path="/app/projects" element={<ProjectsPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProjectsPage — workflow type", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("offers a workflow picker and sends the choice on create", async () => {
    const mock = stubFetch();
    renderPage();

    const openers = await screen.findAllByRole("button", { name: "New project" });
    fireEvent.click(openers[0]);

    // the workflow picker is on the create form
    expect(await screen.findByText("Workflow")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("e.g. Tower A Lobby Cladding"), {
      target: { value: "Parallel build" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));

    await waitFor(() => {
      const post = mock.mock.calls.find(([u, i]) =>
        String(u).endsWith("/projects") && (i as RequestInit)?.method === "POST");
      expect(post).toBeTruthy();
      const body = JSON.parse(String((post![1] as RequestInit).body));
      expect(body.name).toBe("Parallel build");
      expect(body.workflow_type).toBe("sequential"); // default; picker feeds this field
    });
  });
});
