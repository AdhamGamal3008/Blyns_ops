// Quick actions render exactly what the server returns, in server order (already
// ranked by role × recent behavior). The UI contract: lead with the first as
// primary, keep five inline, and put the rest behind a "More" overflow menu so
// every permitted action stays reachable (Phase 1 — acceptance §6).

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { QuickActions } from "../client/dashboard/QuickActions";

const { navigate } = vi.hoisted(() => ({ navigate: vi.fn() }));
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigate };
});

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

const action = (n: number) => ({
  key: `a.${n}`, label: `Action ${n}`, module: "crm",
  required_level: 3, target_route: `/app/route/${n}`,
});
const seven = Array.from({ length: 7 }, (_, i) => action(i + 1));

function mount(data: unknown[]) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okJson({ data })));
  render(<MemoryRouter><QuickActions /></MemoryRouter>);
}

const prefsRows = [
  { key: "project.new", label: "New Project", module: "projects", pinned: false, hidden: false },
  { key: "crm.lead.new", label: "New Lead", module: "crm", pinned: false, hidden: false },
  { key: "finance.bill.new", label: "New Bill", module: "finance", pinned: false, hidden: false },
];

// Route-aware stub: the ranked list (with meta.customizable) on the main path,
// the full editable set on /prefs, and it echoes back PUTs.
function stubRoutes() {
  const mock = vi.fn(async (url: string, _init?: RequestInit) => {
    const u = String(url);
    if (u.endsWith("/dashboard/quick-actions/prefs")) return okJson({ data: prefsRows });
    if (u.endsWith("/dashboard/quick-actions")) {
      return okJson({ data: seven, meta: { customizable: true } });
    }
    return okJson({ data: [] });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

describe("QuickActions", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    navigate.mockClear();
  });

  it("renders one button per server-permitted action", async () => {
    mount([
      { key: "crm.lead.new", label: "New Lead", module: "crm",
        required_level: 3, target_route: "/app/crm/leads/new" },
      { key: "project.new", label: "New Project", module: "projects",
        required_level: 3, target_route: "/app/projects/new" },
    ]);
    await waitFor(() => {
      expect(screen.getByText("New Lead")).toBeInTheDocument();
      expect(screen.getByText("New Project")).toBeInTheDocument();
    });
    expect(screen.queryByText("New Invoice")).not.toBeInTheDocument();
    // nothing spilled to an overflow menu when everything fits inline
    expect(screen.queryByRole("button", { name: /more/i })).not.toBeInTheDocument();
  });

  it("renders nothing when the role permits no actions", async () => {
    mount([]);
    const { container } = render(<MemoryRouter><QuickActions /></MemoryRouter>);
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("keeps five inline (first as primary) and hides the rest behind More", async () => {
    mount(seven);
    await waitFor(() => expect(screen.getByText("Action 1")).toBeInTheDocument());

    for (const n of [1, 2, 3, 4, 5]) {
      expect(screen.getByRole("button", { name: `Action ${n}` })).toBeInTheDocument();
    }
    // the sixth and seventh live in the closed menu, so they are not yet rendered
    expect(screen.queryByRole("button", { name: "Action 6" })).not.toBeInTheDocument();
    expect(screen.queryByText("Action 7")).not.toBeInTheDocument();

    // the leading action is the primary; the second is not
    expect(screen.getByRole("button", { name: "Action 1" }).className).toMatch(/primary/);
    expect(screen.getByRole("button", { name: "Action 2" }).className).not.toMatch(/primary/);

    expect(screen.getByRole("button", { name: /more/i })).toBeInTheDocument();
  });

  it("navigates to an inline action's route on click", async () => {
    mount(seven);
    await waitFor(() => expect(screen.getByText("Action 2")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Action 2" }));
    expect(navigate).toHaveBeenCalledWith("/app/route/2");
  });

  it("reaches an overflow action through the More menu and navigates", async () => {
    mount(seven);
    const more = await screen.findByRole("button", { name: /more/i });
    // Radix opens the menu from the keyboard reliably in jsdom (pointer capture
    // isn't implemented there); Enter opens it and focuses the first item.
    fireEvent.keyDown(more, { key: "Enter" });

    const item = await screen.findByRole("menuitem", { name: "Action 7" });
    fireEvent.click(item);
    expect(navigate).toHaveBeenCalledWith("/app/route/7");
  });

  it("offers a Customize control that opens the dialog", async () => {
    stubRoutes();
    render(<MemoryRouter><QuickActions /></MemoryRouter>);
    const gear = await screen.findByRole("button", { name: /customize quick actions/i });
    fireEvent.click(gear);
    expect(await screen.findByText("Customize quick actions")).toBeInTheDocument();
    // rows come from /prefs — every permitted action, including any hidden
    expect(await screen.findByText("New Bill")).toBeInTheDocument();
  });

  it("saves the chosen pins and hides", async () => {
    const mock = stubRoutes();
    render(<MemoryRouter><QuickActions /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /customize quick actions/i }));

    fireEvent.change(await screen.findByLabelText("New Project placement"),
      { target: { value: "pinned" } });
    fireEvent.change(screen.getByLabelText("New Bill placement"),
      { target: { value: "hidden" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      const put = mock.mock.calls.find(
        ([url, init]) =>
          String(url).endsWith("/dashboard/quick-actions/prefs") && init?.method === "PUT",
      );
      expect(put).toBeTruthy();
      expect(JSON.parse(String(put![1]!.body))).toEqual({
        pinned: ["project.new"], hidden: ["finance.bill.new"],
      });
    });
  });
});
