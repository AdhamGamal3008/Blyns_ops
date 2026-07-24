// Calendar quick view (docs/modules/CLIENT_DASHBOARD.md §2). The contract:
// every calendar entry opens its detail on hover AND on click/keyboard — hover
// alone is unreachable for keyboard and touch — and the detail deep-links to
// the source entity.

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CalendarView } from "../client/dashboard/CalendarView";
import type { CalendarEvent } from "../shared/types";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

// Mid-month so the day is never in an adjacent-month cell. All-day events are
// calendar dates stored at UTC midnight; timed ones are moments, so they are
// built at local noon — far enough from either midnight that the day is the
// same however the test machine's timezone is set.
function allDayOn(day: number): string {
  const now = new Date();
  return new Date(Date.UTC(now.getFullYear(), now.getMonth(), day)).toISOString();
}

function timedOn(day: number, hour: number): string {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), day, hour).toISOString();
}

const DEAL: CalendarEvent = {
  id: "crm:deal_close:d1", source_module: "crm", type: "deal_close",
  title: "Retrofit deal", start: allDayOn(12), end: null, all_day: true,
  entity_ref: { module: "crm", type: "deal", id: "d1" }, color_key: "crm",
  meta: { amount: 42000, currency: "USD", stage: "proposal", probability_pct: 60 },
};

const INVOICE: CalendarEvent = {
  id: "finance:invoice_due:i1", source_module: "finance", type: "invoice_due",
  title: "Invoice INV-0042 due", start: allDayOn(12), end: null, all_day: true,
  entity_ref: { module: "finance", type: "invoice", id: "i1" }, color_key: "finance",
  meta: {
    counterparty: "Northwind Traders", total: 1000, paid: 250, balance: 750,
    currency: "USD", status: "partly_paid",
  },
};

const MILESTONE: CalendarEvent = {
  id: "projects:milestone:p1:kick", source_module: "projects", type: "milestone",
  title: "Tower fit-out — Kickoff", start: allDayOn(12), end: null, all_day: true,
  entity_ref: { module: "projects", type: "project", id: "p1" }, color_key: "projects",
  meta: { project: "Tower fit-out", code: "PRJ-0009", status: "active", stage_order: 7 },
};

const TASK: CalendarEvent = {
  id: "crm:task_due:a1", source_module: "crm", type: "task_due",
  title: "Send proposal", start: timedOn(12, 12), end: null, all_day: false,
  entity_ref: { module: "crm", type: "activity", id: "a1" }, color_key: "crm",
  meta: { activity_type: "task", about: "deal", notes: "Include the revised BOM" },
};

function stubFetch(events: CalendarEvent[]) {
  const mock = vi.fn(async (url: string) =>
    String(url).includes("/calendar") ? okJson({ data: events }) : okJson({ data: [] }),
  );
  vi.stubGlobal("fetch", mock);
  return mock;
}

function renderCalendar(events: CalendarEvent[]) {
  stubFetch(events);
  return render(
    <MemoryRouter>
      <CalendarView />
    </MemoryRouter>,
  );
}

async function chips() {
  await waitFor(() =>
    expect(screen.getAllByTestId("calendar-chip").length).toBeGreaterThan(0));
  return screen.getAllByTestId("calendar-chip");
}

describe("Calendar quick view", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("renders every entry as a focusable button, not inert text", async () => {
    renderCalendar([DEAL, INVOICE]);
    const all = await chips();
    expect(all).toHaveLength(2);
    for (const chip of all) {
      expect(chip.tagName).toBe("BUTTON");
      // reachable by keyboard: a button is tabbable unless disabled
      expect(chip).not.toBeDisabled();
    }
  });

  it("opens the detail on click and shows the source fields", async () => {
    renderCalendar([DEAL]);
    const [chip] = await chips();
    fireEvent.click(chip);

    const panel = await screen.findByRole("dialog");
    expect(within(panel).getByText("Retrofit deal")).toBeInTheDocument();
    expect(within(panel).getByText("Expected close")).toBeInTheDocument();
    // the numbers a reader wants before deciding to open the record
    expect(within(panel).getByText("$42,000")).toBeInTheDocument();
    expect(within(panel).getByText("proposal")).toBeInTheDocument();
    expect(within(panel).getByText("60%")).toBeInTheDocument();
  });

  it("opens the same detail on hover", async () => {
    renderCalendar([DEAL]);
    const [chip] = await chips();
    fireEvent.mouseEnter(chip);

    const panel = await screen.findByRole("dialog");
    expect(within(panel).getByText("Retrofit deal")).toBeInTheDocument();
  });

  it("a hovered panel closes on leave, but a clicked one stays put", async () => {
    renderCalendar([DEAL]);
    const [chip] = await chips();

    fireEvent.mouseEnter(chip);
    await screen.findByRole("dialog");
    fireEvent.mouseLeave(chip);
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    // clicking pins it: the pointer must be free to travel to the panel's link
    fireEvent.click(chip);
    await screen.findByRole("dialog");
    fireEvent.mouseLeave(chip);
    await new Promise((r) => setTimeout(r, 200));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("closes a pinned panel on Escape", async () => {
    renderCalendar([DEAL]);
    const [chip] = await chips();
    fireEvent.click(chip);
    await screen.findByRole("dialog");

    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("deep-links to the source entity — a project to its own page", async () => {
    renderCalendar([MILESTONE]);
    const [chip] = await chips();
    fireEvent.click(chip);

    const panel = await screen.findByRole("dialog");
    expect(within(panel).getByText("PRJ-0009")).toBeInTheDocument();
    expect(within(panel).getByRole("link", { name: /Open in projects/i }))
      .toHaveAttribute("href", "/app/projects/p1");
  });

  it("shows an invoice's outstanding balance, not just its face total", async () => {
    renderCalendar([INVOICE]);
    const [chip] = await chips();
    fireEvent.click(chip);

    const panel = await screen.findByRole("dialog");
    expect(within(panel).getByText("Northwind Traders")).toBeInTheDocument();
    expect(within(panel).getByText("$750")).toBeInTheDocument();   // still owed
    expect(within(panel).getByText("$1,000")).toBeInTheDocument(); // of this
    expect(within(panel).getByText("partly paid")).toBeInTheDocument();
    expect(within(panel).getByRole("link", { name: /Open in finance/i }))
      .toHaveAttribute("href", "/app/finance");
  });

  it("shows the time for a timed entry and its notes", async () => {
    renderCalendar([TASK]);
    const [chip] = await chips();
    fireEvent.click(chip);

    const panel = await screen.findByRole("dialog");
    expect(within(panel).getByText("Task due")).toBeInTheDocument();
    expect(within(panel).getByText("Include the revised BOM")).toBeInTheDocument();
    // a timed event is not announced as all-day
    expect(within(panel).queryByText(/all day/)).not.toBeInTheDocument();
  });

  it("+N more opens the day's full list, each row deep-linking", async () => {
    renderCalendar([DEAL, INVOICE, MILESTONE, TASK]);
    await chips();
    // only the first three fit in a cell
    expect(screen.getAllByTestId("calendar-chip")).toHaveLength(3);

    const more = screen.getByTestId("calendar-more");
    expect(more).toHaveTextContent("+1 more");
    fireEvent.click(more);

    const panel = await screen.findByRole("dialog");
    expect(within(panel).getByText("4 scheduled items")).toBeInTheDocument();
    for (const e of [DEAL, INVOICE, MILESTONE, TASK]) {
      expect(within(panel).getByText(e.title)).toBeInTheDocument();
    }
    expect(within(panel).getByRole("link", { name: /Tower fit-out/ }))
      .toHaveAttribute("href", "/app/projects/p1");
  });

  it("survives an event with no meta at all", async () => {
    const bare = { ...DEAL, meta: undefined };
    renderCalendar([bare]);
    const [chip] = await chips();
    fireEvent.click(chip);

    const panel = await screen.findByRole("dialog");
    expect(within(panel).getByText("Retrofit deal")).toBeInTheDocument();
    expect(within(panel).getByRole("link", { name: /Open in crm/i })).toBeInTheDocument();
  });
});
