// IP access admin panel (docs/IP_ACCESS_CONTROL_PLAN.md §2-F): the two lists, the
// add form, the IP checker, and the "would block your current IP" warning.

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { IpRulesPage } from "../admin/IpRulesPage";
import type { IpRule } from "../shared/types";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

const RULES: IpRule[] = [
  {
    id: "d1", kind: "deny", match_type: "cidr", value: "203.0.113.0/24",
    reason: "abuse", enabled: true, source: "manual", family: 4,
  },
  {
    id: "a1", kind: "allow", match_type: "ip", value: "198.51.100.7",
    reason: null, enabled: true, source: "seed", family: 4,
  },
];

const WHOAMI = { ip: "203.0.113.5", country: "US" };

type FetchMock = ReturnType<typeof vi.fn>;

function stubFetch(over: { rules?: IpRule[]; testResult?: unknown } = {}): FetchMock {
  const rules = over.rules ?? RULES;
  const mock = vi.fn(async (url: string | URL, init?: RequestInit) => {
    const u = String(url);
    const method = (init?.method ?? "GET").toUpperCase();
    if (u.includes("/ip-rules/whoami")) return okJson({ data: WHOAMI });
    if (u.includes("/ip-rules/test")) {
      return okJson({
        data: over.testResult ?? {
          ip: "203.0.113.9", country: "US", allowed: false, reason: "denied",
          matched_rule: {
            id: "d1", kind: "deny", match_type: "cidr", value: "203.0.113.0/24",
          },
        },
      });
    }
    if (method === "GET") return okJson({ data: rules });
    if (method === "POST") {
      return okJson({
        data: {
          id: "new", kind: "deny", match_type: "ip", value: "9.9.9.9",
          reason: null, enabled: true, source: "manual", family: 4,
        },
      });
    }
    if (method === "PATCH") return okJson({ data: { ...rules[0], enabled: false } });
    if (method === "DELETE") return okJson({ data: { deleted: true } });
    return okJson({ data: [] });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

type Call = [string | URL, RequestInit?];
const callsOf = (m: FetchMock): Call[] => m.mock.calls as unknown as Call[];

const findCall = (m: FetchMock, method: string, includes: string) =>
  callsOf(m).find(
    ([u, o]) =>
      String(u).includes(includes) && (o?.method ?? "GET").toUpperCase() === method,
  );

const createCall = (m: FetchMock) =>
  callsOf(m).find(([u, o]) => String(u).endsWith("/ip-rules") && o?.method === "POST");

describe("IpRulesPage", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("renders the deny and allow lists from the API", async () => {
    stubFetch();
    render(<IpRulesPage />);
    await waitFor(() =>
      expect(screen.getByText("203.0.113.0/24")).toBeInTheDocument(),
    );
    expect(screen.getByText("198.51.100.7")).toBeInTheDocument();
    expect(screen.getByText("Denylist")).toBeInTheDocument();
    expect(screen.getByText("Allowlist")).toBeInTheDocument();
  });

  it("toggles a rule with a PATCH of the flipped enabled flag", async () => {
    const m = stubFetch();
    render(<IpRulesPage />);
    await waitFor(() => screen.getByText("203.0.113.0/24"));

    fireEvent.click(
      screen.getByRole("switch", { name: /disable rule 203\.0\.113\.0\/24/i }),
    );
    await waitFor(() => expect(findCall(m, "PATCH", "/ip-rules/d1")).toBeTruthy());
    const [, opts] = findCall(m, "PATCH", "/ip-rules/d1")!;
    expect(JSON.parse((opts as RequestInit).body as string)).toEqual({ enabled: false });
  });

  it("deletes a rule with a DELETE", async () => {
    const m = stubFetch();
    render(<IpRulesPage />);
    await waitFor(() => screen.getByText("203.0.113.0/24"));

    fireEvent.click(
      screen.getByRole("button", { name: /delete rule 203\.0\.113\.0\/24/i }),
    );
    await waitFor(() => expect(findCall(m, "DELETE", "/ip-rules/d1")).toBeTruthy());
  });

  it("checks an IP and shows the verdict from /test", async () => {
    const m = stubFetch();
    render(<IpRulesPage />);
    await waitFor(() => screen.getByText("203.0.113.0/24"));

    fireEvent.change(screen.getByLabelText("IP address to check"), {
      target: { value: "203.0.113.9" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Check" }));

    await waitFor(() =>
      expect(screen.getByText(/matches a deny rule on CIDR/i)).toBeInTheDocument(),
    );
    expect(findCall(m, "POST", "/ip-rules/test")).toBeTruthy();
  });

  it("adds a rule through the form", async () => {
    const m = stubFetch();
    render(<IpRulesPage />);
    await waitFor(() => screen.getByText("203.0.113.0/24"));

    fireEvent.click(screen.getByRole("button", { name: "Add rule" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByPlaceholderText("203.0.113.5"), {
      target: { value: "9.9.9.9" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add rule" }));

    await waitFor(() => expect(createCall(m)).toBeTruthy());
    const [, opts] = createCall(m)!;
    expect(JSON.parse((opts as RequestInit).body as string)).toMatchObject({
      kind: "deny", match_type: "ip", value: "9.9.9.9", enabled: true,
    });
  });

  it("warns when a new deny rule would block the admin's own IP", async () => {
    stubFetch();
    render(<IpRulesPage />);
    await waitFor(() => screen.getByText("203.0.113.0/24"));

    fireEvent.click(screen.getByRole("button", { name: "Add rule" }));
    const dialog = await screen.findByRole("dialog");
    // Defaults are deny + IP; typing the admin's own IP (from /whoami) trips the guard.
    fireEvent.change(within(dialog).getByPlaceholderText("203.0.113.5"), {
      target: { value: "203.0.113.5" },
    });
    await waitFor(() =>
      expect(
        within(dialog).getByText(/would block your current IP/i),
      ).toBeInTheDocument(),
    );
  });
});
