// Role editor contract (docs/ADMIN_PORTAL.md §3 / SETTINGS.md §1.3): every
// client resource with a 4-way None/View/Read/Write selector.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RoleEditor, RolesSection } from "../client/settings/RolesSection";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

describe("RolesSection", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("lists roles with their permission levels", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okJson({
      data: [{
        id: "r1", name: "Owner", is_system: true,
        permissions: { dashboard: 3, calendar: 3, activity: 3, projects: 3,
                       crm: 3, inventory: 3, finance: 3, settings: 3 },
      }, {
        id: "r2", name: "Viewer", is_system: true,
        permissions: { dashboard: 2, calendar: 2, activity: 0, projects: 0,
                       crm: 0, inventory: 0, finance: 0, settings: 0 },
      }],
    })));
    render(<RolesSection canWrite={true} />);
    await waitFor(() => {
      expect(screen.getByText("Owner")).toBeInTheDocument();
      expect(screen.getByText("Viewer")).toBeInTheDocument();
    });
    expect(screen.getAllByText("Write").length).toBeGreaterThan(1);
  });

  it("editor renders a 4-way selector per resource and submits the map", async () => {
    const fetchMock = vi.fn().mockResolvedValue(okJson({ data: { id: "r9" } }));
    vi.stubGlobal("fetch", fetchMock);
    const onDone = vi.fn();
    render(<RoleEditor role={null} onDone={onDone} />);

    // 8 client resources × 4 levels of radios
    expect(document.querySelectorAll('input[type="radio"]').length).toBe(8 * 4);

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Estimator" } });
    // grant crm = Read (level index 2)
    const crmRadios = document.querySelectorAll('input[name="perm-crm"]');
    fireEvent.click(crmRadios[2]);
    fireEvent.click(screen.getByText("Save role"));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    const [url, opts] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/settings/roles");
    const body = JSON.parse(opts.body);
    expect(body.name).toBe("Estimator");
    expect(body.permissions.crm).toBe(2);
    expect(body.permissions.finance).toBe(0);
  });
});
