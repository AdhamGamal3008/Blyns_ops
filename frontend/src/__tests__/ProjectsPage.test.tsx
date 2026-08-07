// Portfolio list (docs/modules/PROJECT_MANAGEMENT.md §12): rows render from the
// server and a WRITE user can create a project, which posts to /projects.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectsPage } from "../client/projects/ProjectsPage";
import type { ClientMe } from "../shared/types";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

const PROJECTS = {
  data: [
    { id: "p1", code: "PRJ-0001", name: "Tower A Lobby Cladding",
      current_stage_order: 3, current_stage_key: "site_survey", status: "active",
      budget: { planned: 50000, committed: 0, actual: 0, currency: "USD" },
      created_at: "2026-07-01T00:00:00Z" },
  ],
};

function me(level: number, analytics = 0): ClientMe {
  return {
    id: "u1", email: "o@acme.com", name: "Owner", must_reset_password: false,
    company: { slug: "acme", name: "Acme", enabled_modules: ["projects"] },
    role: {
      id: "r1", name: "Owner",
      permissions: { projects: level, projects_analytics: analytics } as never,
    },
  };
}

// the machine's length drives the "X/N" denominator — nine stages in v2.0
const STAGES = { data: Array.from({ length: 9 }, (_, i) => ({ order: i + 1 })) };

const ANALYTICS = {
  data: {
    kpis: {
      active: 1, on_hold_blocked: 0, overdue: 0, open_exceptions: 0,
      budget: { planned: 0, actual: 0, committed: 0, variance: 0, variance_pct: null },
    },
  },
};

function stubFetch() {
  const mock = vi.fn(async (url: string, _init?: RequestInit) => {
    const u = String(url);
    if (u.includes("/crm/accounts")) return okJson({ data: [] });
    if (u.includes("/projects/config/stages")) return okJson(STAGES);
    if (u.includes("/projects/analytics")) return okJson(ANALYTICS);
    if (u.includes("/projects")) return okJson(PROJECTS);
    return okJson({ data: {} });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

function renderPage(level: number, analytics = 0) {
  return render(
    <MemoryRouter initialEntries={["/app/projects"]}>
      <Routes>
        <Route element={<Provider level={level} analytics={analytics} />}>
          <Route path="/app/projects" element={<ProjectsPage />} />
          <Route path="/app/projects/:id" element={<div>detail page</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}
function Provider(props: { level: number; analytics: number }) {
  return <Outlet context={me(props.level, props.analytics)} />;
}

const postCall = (mock: ReturnType<typeof stubFetch>) =>
  mock.mock.calls.find(([u, init]) =>
    init?.method === "POST" && String(u).endsWith("/projects"));

describe("ProjectsPage", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("lists projects with their current stage", async () => {
    stubFetch();
    renderPage(3);
    await waitFor(() =>
      expect(screen.getByText("Tower A Lobby Cladding")).toBeInTheDocument());
    expect(screen.getByText("PRJ-0001")).toBeInTheDocument();
    expect(screen.getByText(/3\/9 · Site survey/)).toBeInTheDocument();
  });

  it("shows an Analytics tab only when the role has analytics access", async () => {
    stubFetch();
    renderPage(3, 1); // projects WRITE + projects_analytics VIEW
    await waitFor(() =>
      expect(screen.getByText("Tower A Lobby Cladding")).toBeInTheDocument());
    expect(screen.getByRole("tab", { name: "Portfolio" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Analytics" })).toBeInTheDocument();
  });

  it("hides the Analytics tab (no tabs at all) without analytics access", async () => {
    stubFetch();
    renderPage(3, 0);
    await waitFor(() =>
      expect(screen.getByText("Tower A Lobby Cladding")).toBeInTheDocument());
    expect(screen.queryByRole("tab", { name: "Analytics" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Portfolio" })).not.toBeInTheDocument();
  });

  it("lets a WRITE user create a project", async () => {
    const mock = stubFetch();
    renderPage(3);
    await waitFor(() =>
      expect(screen.getByText("Tower A Lobby Cladding")).toBeInTheDocument());

    fireEvent.click(screen.getByText("New project"));
    await waitFor(() => expect(screen.getByText("Create project")).toBeInTheDocument());

    const name = document.querySelector('input[placeholder^="e.g."]')!;
    fireEvent.change(name, { target: { value: "New Fitout" } });
    fireEvent.click(screen.getByText("Create project"));

    await waitFor(() => {
      const post = postCall(mock);
      expect(post).toBeTruthy();
      expect(JSON.parse(String(post![1]!.body)).name).toBe("New Fitout");
    });
  });

  it("hides create from a READ-only user", async () => {
    stubFetch();
    renderPage(2);
    await waitFor(() =>
      expect(screen.getByText("Tower A Lobby Cladding")).toBeInTheDocument());
    expect(screen.queryByText("New project")).not.toBeInTheDocument();
  });
});
