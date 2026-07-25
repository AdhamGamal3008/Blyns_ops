// Products edit contract (docs/modules/INVENTORY.md §1/§7): a writer can edit a
// product in place; the dialog pre-fills from the row and PATCHes it (audited as
// inventory.product.updated). Read-only users get no write controls.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProductsSection } from "../client/inventory/ProductsSection";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

const PRODUCTS = {
  data: [
    {
      id: "p1", sku: "OAK-01", name: "Oak panel", category: "Timber",
      description: "Kiln-dried", barcode: "590123", unit: "pcs",
      cost_price: 12, sale_price: 24, currency: "USD",
      reorder_point: 20, reorder_qty: 100, is_active: true,
    },
  ],
};

function stubFetch() {
  const mock = vi.fn(async (url: string, _init?: RequestInit) =>
    String(url).includes("/inventory/products") ? okJson(PRODUCTS) : okJson({ data: {} }),
  );
  vi.stubGlobal("fetch", mock);
  return mock;
}

const call = (mock: ReturnType<typeof stubFetch>, method: string) =>
  mock.mock.calls.find(([, init]) => init?.method === method);

describe("ProductsSection edit", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("pre-fills the edit dialog from the row and PATCHes the changes", async () => {
    const mock = stubFetch();
    render(<ProductsSection canWrite={true} />);
    await waitFor(() => expect(screen.getByText("Oak panel")).toBeInTheDocument());

    fireEvent.click(screen.getByText("Edit"));
    await waitFor(() =>
      expect(screen.getByText("Edit Oak panel")).toBeInTheDocument());

    // the dialog opens populated with the product's current values
    expect(screen.getByDisplayValue("OAK-01")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Oak panel")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Kiln-dried")).toBeInTheDocument();
    expect(screen.getByDisplayValue("20")).toBeInTheDocument();  // reorder point

    fireEvent.change(screen.getByDisplayValue("Oak panel"), {
      target: { value: "Oak panel 2m" },
    });
    fireEvent.change(screen.getByDisplayValue("20"), { target: { value: "15" } });
    fireEvent.click(screen.getByText("Save changes"));

    await waitFor(() => {
      const patch = call(mock, "PATCH");
      expect(patch).toBeTruthy();
      expect(String(patch![0])).toContain("/inventory/products/p1");
      const body = JSON.parse(String(patch![1]!.body));
      expect(body.name).toBe("Oak panel 2m");
      expect(body.reorder_point).toBe(15);
      expect(body.sku).toBe("OAK-01");           // unchanged fields still sent
    });
  });

  it("does not PATCH when opening the create dialog", async () => {
    stubFetch();
    render(<ProductsSection canWrite={true} />);
    await waitFor(() => expect(screen.getByText("Oak panel")).toBeInTheDocument());

    fireEvent.click(screen.getByText("New product"));
    await waitFor(() => expect(screen.getByText("Create product")).toBeInTheDocument());
    expect(screen.getByText("Create product")).toBeInTheDocument();
    // the dialog is empty, not pre-filled from a row
    expect(screen.queryByDisplayValue("Oak panel")).not.toBeInTheDocument();
  });

  it("read-only users get no edit control", async () => {
    stubFetch();
    render(<ProductsSection canWrite={false} />);
    await waitFor(() => expect(screen.getByText("Oak panel")).toBeInTheDocument());
    expect(screen.queryByText("Edit")).not.toBeInTheDocument();
    expect(screen.queryByText("New product")).not.toBeInTheDocument();
  });
});
