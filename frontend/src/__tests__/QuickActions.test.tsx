// Quick actions render exactly what the server returns (the server already
// filtered by role WRITE permissions — acceptance §6).

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { QuickActions } from "../client/dashboard/QuickActions";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

describe("QuickActions", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("renders one button per server-permitted action", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okJson({
      data: [
        { key: "crm.lead.new", label: "New Lead", module: "crm",
          required_level: 3, target_route: "/app/crm/leads/new" },
        { key: "project.new", label: "New Project", module: "projects",
          required_level: 3, target_route: "/app/projects/new" },
      ],
    })));
    render(<MemoryRouter><QuickActions /></MemoryRouter>);
    await waitFor(() => {
      expect(screen.getByText("New Lead")).toBeInTheDocument();
      expect(screen.getByText("New Project")).toBeInTheDocument();
    });
    expect(screen.queryByText("New Invoice")).not.toBeInTheDocument();
  });

  it("renders nothing when the role permits no actions", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okJson({ data: [] })));
    const { container } = render(<MemoryRouter><QuickActions /></MemoryRouter>);
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});
