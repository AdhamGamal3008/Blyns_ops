// Project create form — the Stage-1 configuration picker
// (docs/PROJECT_CONFIGURATIONS_PLAN.md Phase 4).
//
// The dialog offers the workspace's ACTIVE configurations with the default
// preselected, and sends `configuration_id`; the project then pins that
// configuration's current version for life (D1). Driving a Radix Select open needs
// pointer-capture APIs jsdom lacks, so these assert the preselected choice, the
// payload, and the hint — changing the selection is covered by the backend tests
// (test_projects_configurations_crud.py).

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectsPage } from "../client/projects/ProjectsPage";
import type { ClientMe } from "../shared/types";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

const CONFIGS = [
  {
    id: "c1", name: "Standard", workflow_shape: "sequential",
    current_version: 3, is_default: true, is_active: true,
    description: "The default 9-stage pipeline.",
  },
  {
    id: "c2", name: "Flooring — ASTM", workflow_shape: "concurrent",
    current_version: 2, is_default: false, is_active: true,
  },
];

function me(): ClientMe {
  return {
    id: "u1", email: "o@acme.com", name: "Owner", must_reset_password: false,
    company: { slug: "acme", name: "Acme", enabled_modules: ["projects"] },
    role: { id: "r1", name: "Owner", permissions: { projects: 3 } as never },
  };
}

function stubFetch(configs: unknown[] = CONFIGS) {
  const mock = vi.fn(async (url: string, init?: RequestInit) => {
    const u = String(url);
    if (u.includes("/projects/config/configurations")) return okJson({ data: configs });
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

async function openDialog() {
  const openers = await screen.findAllByRole("button", { name: "New project" });
  fireEvent.click(openers[0]);
}

function postBody(mock: ReturnType<typeof stubFetch>) {
  const post = mock.mock.calls.find(([u, i]) =>
    String(u).endsWith("/projects") && (i as RequestInit)?.method === "POST");
  return post ? JSON.parse(String((post[1] as RequestInit).body)) : null;
}

describe("ProjectsPage — configuration picker", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("offers a configuration picker on the create form", async () => {
    stubFetch();
    renderPage();
    await openDialog();

    expect(await screen.findByText("Configuration")).toBeInTheDocument();
  });

  it("only asks for configurations that can still start a project", async () => {
    const mock = stubFetch();
    renderPage();
    await openDialog();

    await waitFor(() => {
      const call = mock.mock.calls.find(([u]) =>
        String(u).includes("/projects/config/configurations"));
      expect(String(call![0])).toContain("active_only=true");
    });
  });

  it("preselects the default and says the version is pinned for life", async () => {
    stubFetch();
    renderPage();
    await openDialog();

    // only Standard (the default) is at version 3, so the hint naming v3 is proof
    // the default was preselected — the Radix trigger's own label does not render
    // in jsdom until the listbox mounts, so the hint is what we can assert on.
    expect(
      await screen.findByText(/keeps version 3 for its whole life/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Stages run one at a time, in order\./)).toBeInTheDocument();
  });

  it("sends configuration_id on create", async () => {
    const mock = stubFetch();
    renderPage();
    await openDialog();
    await screen.findByText("Configuration");   // the picker has loaded its options

    fireEvent.change(screen.getByPlaceholderText("e.g. Tower A Lobby Cladding"), {
      target: { value: "Tower B cladding" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));

    await waitFor(() => {
      const body = postBody(mock);
      expect(body).toBeTruthy();
      expect(body.name).toBe("Tower B cladding");
      expect(body.configuration_id).toBe("c1");   // the default
      expect(body).not.toHaveProperty("workflow_type");
    });
  });

  it("hides the picker on a workspace with no configurations yet", async () => {
    // An un-migrated workspace has none; the backend still accepts a create and
    // falls back to the legacy template (G-1), so the form must not block.
    const mock = stubFetch([]);
    renderPage();
    await openDialog();

    await screen.findByPlaceholderText("e.g. Tower A Lobby Cladding");
    expect(screen.queryByText("Configuration")).not.toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("e.g. Tower A Lobby Cladding"), {
      target: { value: "Legacy workspace" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));

    await waitFor(() => {
      const body = postBody(mock);
      expect(body).toBeTruthy();
      expect(body).not.toHaveProperty("configuration_id");
    });
  });
});
