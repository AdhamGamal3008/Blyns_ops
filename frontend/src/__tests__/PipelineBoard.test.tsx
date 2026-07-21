// Pipeline board contract (docs/modules/CRM.md §3/§6): stage buckets render
// counts + summed amounts, and moving a deal to `lost` must collect a reason
// before the request goes out (acceptance #2).

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PipelineBoard } from "../client/crm/PipelineBoard";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

const PIPELINE = {
  data: {
    pipeline: "default", name: "Default", open_value: 7500,
    stages: [
      { stage: "new", count: 2, amount: 3500, is_terminal: false },
      { stage: "qualified", count: 0, amount: 0, is_terminal: false },
      { stage: "proposal", count: 1, amount: 4000, is_terminal: false },
      { stage: "negotiation", count: 0, amount: 0, is_terminal: false },
      { stage: "won", count: 0, amount: 0, is_terminal: true },
      { stage: "lost", count: 0, amount: 0, is_terminal: true },
    ],
  },
};

const DEALS = {
  data: [
    { id: "d1", title: "Alpha", stage: "new", amount: 1000, currency: "USD" },
    { id: "d2", title: "Beta", stage: "new", amount: 2500, currency: "USD" },
    { id: "d3", title: "Gamma", stage: "proposal", amount: 4000, currency: "USD" },
  ],
};

function stubFetch() {
  const mock = vi.fn(async (url: string, _init?: RequestInit) => {
    if (String(url).includes("/crm/pipeline")) return okJson(PIPELINE);
    if (String(url).includes("/crm/deals")) return okJson(DEALS);
    return okJson({ data: {} });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

/** The PATCH call the board sent, if any. */
function patchCall(mock: ReturnType<typeof stubFetch>) {
  return mock.mock.calls.find(([, init]) => init?.method === "PATCH");
}

describe("PipelineBoard", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("renders every stage bucket with its count and summed amount", async () => {
    stubFetch();
    render(<PipelineBoard canWrite={true} />);

    await waitFor(() => expect(screen.getByText("Alpha")).toBeInTheDocument());
    // empty stages still render as columns (acceptance #3)
    const heads = [...document.querySelectorAll('[data-testid="stage-head"] b')].map((e) => e.textContent);
    expect(heads).toEqual(["new", "qualified", "proposal", "negotiation", "won", "lost"]);
    // each column shows its own summed amount, in stage order
    const totals = [...document.querySelectorAll('[data-testid="stage-total"]')].map((e) => e.textContent);
    expect(totals).toEqual(["$3,500", "$0", "$4,000", "$0", "$0", "$0"]);
    // open pipeline value in the card title
    expect(screen.getByText(/\$7,500 open/)).toBeInTheDocument();
  });

  it("moving a deal to lost asks for a reason before calling the API", async () => {
    const mock = stubFetch();
    render(<PipelineBoard canWrite={true} />);
    await waitFor(() => expect(screen.getByText("Alpha")).toBeInTheDocument());

    const selects = document.querySelectorAll('select[data-testid="deal-stage"]');
    fireEvent.change(selects[0], { target: { value: "lost" } });

    // no PATCH yet — the reason modal opens first
    await waitFor(() => expect(screen.getByText(/Mark .*Alpha.* lost/)).toBeInTheDocument());
    expect(patchCall(mock)).toBeUndefined();

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "price" } });
    fireEvent.click(screen.getByText("Mark lost"));

    await waitFor(() => {
      const patch = patchCall(mock);
      expect(patch).toBeTruthy();
      expect(patch![0]).toContain("/crm/deals/d1/stage");
      expect(JSON.parse(String(patch![1]!.body))).toEqual({
        stage: "lost", lost_reason: "price",
      });
    });
  });

  it("a non-moving stage change PATCHes straight through", async () => {
    const mock = stubFetch();
    render(<PipelineBoard canWrite={true} />);
    await waitFor(() => expect(screen.getByText("Alpha")).toBeInTheDocument());

    const selects = document.querySelectorAll('select[data-testid="deal-stage"]');
    fireEvent.change(selects[0], { target: { value: "qualified" } });

    await waitFor(() => {
      const patch = patchCall(mock);
      expect(patch).toBeTruthy();
      expect(JSON.parse(String(patch![1]!.body))).toEqual({ stage: "qualified" });
    });
  });

  it("read-only users get no stage controls", async () => {
    stubFetch();
    render(<PipelineBoard canWrite={false} />);
    await waitFor(() => expect(screen.getByText("Alpha")).toBeInTheDocument());
    expect(document.querySelectorAll('select[data-testid="deal-stage"]').length).toBe(0);
    expect(screen.queryByText("New deal")).not.toBeInTheDocument();
  });
});
