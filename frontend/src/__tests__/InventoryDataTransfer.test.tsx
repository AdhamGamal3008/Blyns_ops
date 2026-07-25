// Inventory CSV UI (docs/modules/INVENTORY.md §7). Same shared component as
// CRM, but Inventory is where its per-entity behaviour matters: a derived data
// set offers no Import at all, and an append-only ledger must not claim that
// re-importing "updates" anything.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DataTransfer } from "../shared/csv/DataTransfer";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

const field = (key: string, header: string, extra = {}) => ({
  key, header, kind: "str", required: false, choices: [],
  importable: true, exportable: true, example: "", hint: "", ...extra,
});

const MOVEMENTS = {
  data: {
    entity: "movements", label: "Movements",
    importable: true, append_only: true,
    fields: [
      field("sku_ref", "SKU", { required: true }),
      field("warehouse_code", "Warehouse", { required: true }),
      field("type", "Type", { kind: "enum", choices: ["receipt", "issue"] }),
      field("qty", "Qty", { kind: "float" }),
    ],
    filters: {
      status: { label: "Type", choices: ["receipt", "issue"] },
      date_fields: [{ key: "occurred_at", label: "Occurred at" }],
      supports_search: false, supports_owner: true,
    },
  },
};

const STOCK_LEVELS = {
  data: {
    entity: "stock-levels", label: "Stock levels",
    importable: false, append_only: false,
    fields: [
      field("sku_ref", "SKU", { importable: false }),
      field("on_hand", "On hand", { kind: "float", importable: false }),
    ],
    filters: {
      status: null,
      date_fields: [{ key: "updated_at", label: "Updated at" }],
      supports_search: false, supports_owner: true,
    },
  },
};

/** A commit that posted most rows but had one refused for insufficient stock —
 *  a failure the dry run could not have known about. */
const PARTIAL_COMMIT = {
  data: {
    entity: "movements", label: "Movements", mode: "commit", file: "stock.csv",
    rows: 3, created: 2, updated: 0, failed: 1,
    columns: ["sku_ref", "qty"], ignored_columns: [],
    errors: [{
      row: 3, column: null, value: "",
      message: "Only 10 on hand in Main WH; cannot move 999.",
    }],
    errors_truncated: false,
  },
};

const VALIDATED = {
  data: { ...PARTIAL_COMMIT.data, mode: "validate", created: 3, failed: 0, errors: [] },
};

function stubFetch(meta: unknown) {
  const mock = vi.fn(async (url: string, init?: RequestInit) => {
    const u = String(url);
    if (u.includes("/fields")) return okJson(meta);
    if (u.includes("/import/") && init?.method === "POST") {
      return okJson(u.includes("mode=commit") ? PARTIAL_COMMIT : VALIDATED);
    }
    return new Response("SKU\r\n", {
      status: 200, headers: { "Content-Type": "text/csv" },
    });
  });
  vi.stubGlobal("fetch", mock);
  vi.stubGlobal("URL", Object.assign(URL, {
    createObjectURL: vi.fn(() => "blob:stub"), revokeObjectURL: vi.fn(),
  }));
  return mock;
}

const csvFile = () =>
  new File(["SKU,Qty\r\nA,1\r\n"], "stock.csv", { type: "text/csv" });

describe("Inventory DataTransfer", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("offers no Import for a derived data set, even to a writer", async () => {
    stubFetch(STOCK_LEVELS);
    render(
      <DataTransfer module="inventory" entity="stock-levels" exportOnly canWrite
        onImported={() => {}} />,
    );
    expect(screen.getByRole("button", { name: "Export" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Import" })).not.toBeInTheDocument();
  });

  it("hits the inventory routes, not the CRM ones", async () => {
    const mock = stubFetch(MOVEMENTS);
    render(
      <DataTransfer module="inventory" entity="movements" canWrite
        onImported={() => {}} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() =>
      expect(screen.getByRole("checkbox", { name: "SKU" })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    await waitFor(() => {
      const call = mock.mock.calls.find(([u]) =>
        String(u).includes("/inventory/export/movements?"));
      expect(call).toBeTruthy();
    });
    expect(mock.mock.calls.every(([u]) => !String(u).includes("/crm/"))).toBe(true);
  });

  it("tells the truth about an append-only ledger", async () => {
    stubFetch(MOVEMENTS);
    render(
      <DataTransfer module="inventory" entity="movements" canWrite
        onImported={() => {}} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Import" }));
    await waitFor(() =>
      expect(screen.getByText("1. Start from the template")).toBeInTheDocument());

    fireEvent.change(document.querySelector('input[type="file"]')!, {
      target: { files: [csvFile()] },
    });
    await waitFor(() => expect(screen.getByText("3 to create")).toBeInTheDocument());

    // it must NOT promise that a repeat import updates rather than duplicates
    expect(screen.getByText(/records the movements a second time/)).toBeInTheDocument();
    expect(screen.queryByText(/instead of duplicating them/)).not.toBeInTheDocument();
  });

  it("shows rows that only failed once they were posted", async () => {
    const onImported = vi.fn();
    stubFetch(MOVEMENTS);
    render(
      <DataTransfer module="inventory" entity="movements" canWrite
        onImported={onImported} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Import" }));
    await waitFor(() =>
      expect(screen.getByText("1. Start from the template")).toBeInTheDocument());

    fireEvent.change(document.querySelector('input[type="file"]')!, {
      target: { files: [csvFile()] },
    });
    // the dry run saw no problem — stock is only claimed at commit
    await waitFor(() => expect(screen.getByText("3 to create")).toBeInTheDocument());
    expect(screen.getByText("0 with problems")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Import 3 rows" }));

    await waitFor(() => expect(onImported).toHaveBeenCalled());
    // the result names what actually happened, including the late failure
    expect(screen.getByText("Imported with some rows skipped")).toBeInTheDocument();
    expect(screen.getByText(/2 created, 0 updated, 1 skipped/)).toBeInTheDocument();
    expect(screen.getByText(/Only 10 on hand in Main WH/)).toBeInTheDocument();
  });
});
