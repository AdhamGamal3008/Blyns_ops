// Inventory Analytics tab (docs/PROJECT_ANALYTICS_PLAN.md §6-D): KPI tiles always,
// each chart block only if present and non-empty; READ shows charts, VIEW only kpis.

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InventoryAnalytics } from "../client/inventory/InventoryAnalytics";
import type { InventoryAnalytics as InvData } from "../shared/types";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

const KPIS: InvData["kpis"] = {
  active_skus: 3, stock_value: 1050, low_stock: 3, out_of_stock: 1, categories: 2,
};

const FULL: InvData = {
  kpis: KPIS,
  value_by_category: [
    { category: "Tools", value: 1000 },
    { category: "Hardware", value: 50 },
  ],
  low_stock_items: [{ sku: "PB", name: "Gadget", on_hand: 0, reorder: 10 }],
  top_products: [{ sku: "PC", name: "Gizmo", value: 1000 }],
  movements: [{ month: "2026-08", received: 15, issued: 4 }],
  stock_status: [
    { status: "Out of stock", count: 1 },
    { status: "Low", count: 2 },
    { status: "Healthy", count: 1 },
  ],
};

function stub(payload: InvData) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) =>
    String(url).includes("/inventory/analytics") ? okJson({ data: payload }) : okJson({ data: {} }),
  ));
}

beforeEach(() => vi.restoreAllMocks());

describe("InventoryAnalytics", () => {
  it("renders the KPI row and every chart at the READ tier", async () => {
    stub(FULL);
    render(<InventoryAnalytics />);

    expect(await screen.findByText("Active SKUs")).toBeInTheDocument();
    expect(screen.getByText("Stock value")).toBeInTheDocument();
    expect(screen.getByText("Out of stock")).toBeInTheDocument();
    expect(screen.getByText("Categories")).toBeInTheDocument();

    expect(screen.getByText("Stock value by category")).toBeInTheDocument();
    expect(screen.getByText("Low-stock items")).toBeInTheDocument();
    expect(screen.getByText("Stock movements — last 6 months")).toBeInTheDocument();
    expect(screen.getByText("Top products by value")).toBeInTheDocument();
    expect(screen.getByText("Stock status")).toBeInTheDocument();
    expect(screen.getByText("Received")).toBeInTheDocument(); // legend label
  });

  it("shows only the KPI row at the VIEW tier", async () => {
    stub({ kpis: KPIS });
    render(<InventoryAnalytics />);

    expect(await screen.findByText("Active SKUs")).toBeInTheDocument();
    expect(screen.queryByText("Stock value by category")).not.toBeInTheDocument();
    expect(screen.queryByText("Stock status")).not.toBeInTheDocument();
  });

  it("hides a chart whose block is present but empty", async () => {
    stub({
      kpis: KPIS,
      value_by_category: [{ category: "Tools", value: 0 }],
      low_stock_items: [],
      top_products: [],
      movements: [{ month: "2026-08", received: 0, issued: 0 }],
      stock_status: [{ status: "Healthy", count: 0 }],
    });
    render(<InventoryAnalytics />);

    expect(await screen.findByText("Active SKUs")).toBeInTheDocument();
    expect(screen.queryByText("Stock value by category")).not.toBeInTheDocument();
    expect(screen.queryByText("Top products by value")).not.toBeInTheDocument();
  });
});
