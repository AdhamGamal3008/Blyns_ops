// Stock view contract (docs/modules/INVENTORY.md §2/§6): on-hand is read from
// the derived cache and never edited here; an adjustment must carry a note; the
// low/negative flags follow the reorder point.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StockSection } from "../client/inventory/StockSection";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

const PRODUCTS = {
  data: [
    { id: "p1", sku: "SKU-LOW", name: "Widget", unit: "pcs", reorder_point: 10,
      reorder_qty: 50, cost_price: 1, sale_price: 2, currency: "USD", is_active: true },
    { id: "p2", sku: "SKU-OK", name: "Gadget", unit: "kg", reorder_point: 5,
      reorder_qty: 0, cost_price: 1, sale_price: 2, currency: "USD", is_active: true },
    { id: "p3", sku: "SKU-NEG", name: "Doohickey", unit: "pcs", reorder_point: 0,
      reorder_qty: 0, cost_price: 1, sale_price: 2, currency: "USD", is_active: true },
  ],
};
const WAREHOUSES = {
  data: [
    { id: "w1", name: "Main WH", code: "WH1", is_active: true },
    { id: "w2", name: "Annex", code: "WH2", is_active: true },
  ],
};
const LEVELS = {
  data: [
    { id: "s1", product_id: "p1", warehouse_id: "w1", on_hand: 3 },   // low
    { id: "s2", product_id: "p2", warehouse_id: "w1", on_hand: 40 },  // ok
    { id: "s3", product_id: "p3", warehouse_id: "w2", on_hand: -2 },  // negative
  ],
};

function stubFetch() {
  const mock = vi.fn(async (url: string, _init?: RequestInit) => {
    const u = String(url);
    if (u.includes("/inventory/stock-levels")) return okJson(LEVELS);
    if (u.includes("/inventory/products")) return okJson(PRODUCTS);
    if (u.includes("/inventory/warehouses")) return okJson(WAREHOUSES);
    return okJson({ data: {} });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

const postCall = (mock: ReturnType<typeof stubFetch>) =>
  mock.mock.calls.find(([, init]) => init?.method === "POST");

describe("StockSection", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("shows on-hand per product/warehouse and flags low + negative rows", async () => {
    stubFetch();
    render(<StockSection canWrite={true} />);
    await waitFor(() => expect(screen.getByText("Widget")).toBeInTheDocument());

    expect(screen.getByText("Annex")).toBeInTheDocument();
    // 3 <= reorder_point 10 → low; 40 > 5 → ok; -2 → negative
    expect(screen.getByText("low")).toBeInTheDocument();
    expect(screen.getByText("ok")).toBeInTheDocument();
    expect(screen.getByText("negative")).toBeInTheDocument();
  });

  it("posts a receipt as a movement rather than editing on-hand", async () => {
    const mock = stubFetch();
    render(<StockSection canWrite={true} />);
    await waitFor(() => expect(screen.getByText("Widget")).toBeInTheDocument());

    fireEvent.click(screen.getByText("New movement"));
    await waitFor(() =>
      expect(screen.getByText("Post movement")).toBeInTheDocument());

    const qty = document.querySelector('input[type="number"]')!;
    fireEvent.change(qty, { target: { value: "25" } });
    fireEvent.click(screen.getByText("Post movement"));

    await waitFor(() => {
      const post = postCall(mock);
      expect(post).toBeTruthy();
      expect(String(post![0])).toContain("/inventory/movements");
      expect(JSON.parse(String(post![1]!.body))).toEqual({
        product_id: "p1", warehouse_id: "w1", type: "receipt", qty: 25, note: null,
      });
    });
  });

  it("requires a note on an adjustment before it can be submitted", async () => {
    const mock = stubFetch();
    render(<StockSection canWrite={true} />);
    await waitFor(() => expect(screen.getByText("Widget")).toBeInTheDocument());

    fireEvent.click(screen.getByText("New movement"));
    await waitFor(() =>
      expect(screen.getByText("Post movement")).toBeInTheDocument());

    const selects = document.querySelectorAll("select");
    fireEvent.change(selects[2], { target: { value: "adjustment" } });

    // the note input becomes required — the browser blocks an empty submit
    await waitFor(() => {
      const note = [...document.querySelectorAll("input")].find(
        (i) => i.getAttribute("placeholder") === "why the count changed");
      expect(note).toBeTruthy();
      expect(note!.required).toBe(true);
    });
    expect(postCall(mock)).toBeUndefined();
  });

  it("read-only users get no movement controls", async () => {
    stubFetch();
    render(<StockSection canWrite={false} />);
    await waitFor(() => expect(screen.getByText("Widget")).toBeInTheDocument());
    expect(screen.queryByText("New movement")).not.toBeInTheDocument();
    expect(screen.queryByText("Transfer")).not.toBeInTheDocument();
  });
});
