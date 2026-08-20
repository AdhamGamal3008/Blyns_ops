// Managed project status in the UI (docs/PROJECT_STATUS_PLAN.md §3.2).
//
// The control must offer exactly the legal moves: archive from anywhere,
// restore to active/on-hold, re-open a completed project — and never offer
// `completed`, which only the stage machine can set.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StatusControl } from "../client/projects/StatusControl";
import { MANUAL_TRANSITIONS } from "../client/projects/types";
import type { Project } from "../client/projects/types";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

function project(status: Project["status"]): Project {
  return {
    id: "p1", code: "PRJ-0001", name: "Tower A", status,
    current_stage_order: 3, current_stage_key: "design_package",
  } as Project;
}

async function openMenu() {
  const trigger = await screen.findByRole("button", { name: /status/i });
  // Radix opens from the keyboard reliably in jsdom (no pointer capture there).
  fireEvent.keyDown(trigger, { key: "Enter" });
}

describe("MANUAL_TRANSITIONS", () => {
  it("never offers completed from any status", () => {
    for (const [from, targets] of Object.entries(MANUAL_TRANSITIONS)) {
      expect(targets, `${from} must not offer completed`).not.toContain("completed");
    }
  });

  it("offers archive from every status (rule 1)", () => {
    for (const [from, targets] of Object.entries(MANUAL_TRANSITIONS)) {
      if (from === "archived") continue; // already there
      expect(targets, `${from} must be archivable`).toContain("archived");
    }
  });

  it("recalls an archived project to active or on hold, never completed (rule 3)", () => {
    expect([...MANUAL_TRANSITIONS.archived]).toEqual(["active", "on_hold"]);
  });
});

describe("StatusControl", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("offers hold and archive for an active project", async () => {
    render(<StatusControl project={project("active")} canWrite onChanged={() => {}} />);
    await openMenu();
    expect(await screen.findByRole("menuitem", { name: /put on hold/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /archive/i })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /complete/i })).not.toBeInTheDocument();
  });

  it("labels the archived project's moves as a restore", async () => {
    render(<StatusControl project={project("archived")} canWrite onChanged={() => {}} />);
    await openMenu();
    expect(await screen.findByRole("menuitem", { name: /restore to active/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /restore on hold/i })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /complete/i })).not.toBeInTheDocument();
  });

  it("calls a completed project's return to work a re-open", async () => {
    render(<StatusControl project={project("completed")} canWrite onChanged={() => {}} />);
    await openMenu();
    expect(await screen.findByRole("menuitem", { name: /re-open project/i })).toBeInTheDocument();
    // completed → on_hold is deliberately not offered: re-open first, then hold
    expect(screen.queryByRole("menuitem", { name: /put on hold/i })).not.toBeInTheDocument();
  });

  it("posts the status change with the reason and refreshes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(okJson({ data: { id: "p1" } }));
    vi.stubGlobal("fetch", fetchMock);
    const onChanged = vi.fn();
    render(<StatusControl project={project("active")} canWrite onChanged={onChanged} />);

    await openMenu();
    fireEvent.click(await screen.findByRole("menuitem", { name: /put on hold/i }));

    const input = await screen.findByRole("textbox");
    fireEvent.change(input, { target: { value: "waiting on client sign-off" } });
    fireEvent.click(screen.getByRole("button", { name: /put on hold/i }));

    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    const [url, opts] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/projects/p1/status");
    expect((opts as RequestInit).method).toBe("POST");
    expect(JSON.parse((opts as RequestInit).body as string)).toEqual({
      status: "on_hold", reason: "waiting on client sign-off",
    });
  });

  it("renders nothing for a read-only user", () => {
    const { container } = render(
      <StatusControl project={project("active")} canWrite={false} onChanged={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
