// Role editor contract (docs/ADMIN_PORTAL.md §3 / SETTINGS.md §1.3): every
// client resource with a 4-way None/View/Read/Write selector.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CLIENT_RESOURCES } from "../client/settings/RoleMatrix";
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

  // The editor fetches the CSV-tab catalog on mount, so the mock returns a fresh
  // Response per call (a single shared Response's body can only be read once) and
  // answers the catalog route explicitly.
  function editorFetch(catalog: unknown[] = []) {
    return vi.fn(async (url: string, _init?: RequestInit) => {
      if (String(url).includes("/settings/csv-catalog")) {
        return okJson({ data: catalog });
      }
      return okJson({ data: { id: "r9" } });
    });
  }

  const postCall = (mock: ReturnType<typeof editorFetch>) =>
    mock.mock.calls.find(([, o]) => (o as RequestInit | undefined)?.method === "POST")!;

  it("editor renders a 4-way selector per resource and submits the map", async () => {
    const fetchMock = editorFetch();
    vi.stubGlobal("fetch", fetchMock);
    const onDone = vi.fn();
    render(<RoleEditor role={null} onDone={onDone} />);

    // one 4-way None/View/Read/Write radio group per client resource
    expect(document.querySelectorAll('input[type="radio"]').length).toBe(
      CLIENT_RESOURCES.length * 4,
    );

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Estimator" } });
    // grant crm = Read (level index 2)
    const crmRadios = document.querySelectorAll('input[name="perm-crm"]');
    fireEvent.click(crmRadios[2]);
    fireEvent.click(screen.getByText("Save role"));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    const [url, opts] = postCall(fetchMock);
    expect(String(url)).toContain("/settings/roles");
    const body = JSON.parse((opts as RequestInit).body as string);
    expect(body.name).toBe("Estimator");
    expect(body.permissions.crm).toBe(2);
    expect(body.permissions.finance).toBe(0);
    // the new CSV-grant dimension travels with the role, empty by default
    expect(body.csv_access).toEqual({ export: [], import: [], approve_import: [] });
  });

  it("grants CSV tabs from the catalog and submits them", async () => {
    const fetchMock = editorFetch([
      { key: "crm:accounts", module: "crm", entity: "accounts",
        label: "Crm · Accounts", importable: true },
      { key: "inventory:stock-levels", module: "inventory", entity: "stock-levels",
        label: "Inventory · Stock levels", importable: false },
    ]);
    vi.stubGlobal("fetch", fetchMock);
    const onDone = vi.fn();
    render(<RoleEditor role={null} onDone={onDone} />);

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Exporter" } });

    // the Export picker lists every tab (a derived, export-only one included)
    const trigger = await screen.findByRole("button", { name: /Export: none/ });
    fireEvent.click(trigger);
    const tab = await screen.findByRole("checkbox", { name: "Crm · Accounts" });
    fireEvent.click(tab);

    fireEvent.click(screen.getByText("Save role"));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    const body = JSON.parse((postCall(fetchMock)[1] as RequestInit).body as string);
    expect(body.csv_access.export).toEqual(["crm:accounts"]);
  });
});
