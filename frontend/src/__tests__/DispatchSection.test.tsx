// Production Phase 4 UI (docs/PRODUCTION_MODULE_PLAN.md §6): the Dispatch board
// lists packed → staged → shipped work orders and opens the generated manifest.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DispatchSection } from "../client/production/DispatchSection";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

const BOARD = {
  data: [
    {
      id: "w1", code: "WO-0001-01", project_id: "p1", project_code: "PRJ-0001",
      client_name: "Acme", item_name: "Lobby panels", bom_lines: [],
      qty: { ordered: 10, done: 10 }, station_route: [], current_station_id: null,
      station_name: null, due_date: null, status: "staged", revision_conflict: false,
      packing: {
        type: "pallet", protection_spec: "edge guards", moisture_barrier_ref: "VCI/poly barrier",
        labels: ["WO-0001-01"], handling: [],
      },
      dispatch: {
        load: { units: 10, lines: 1 }, vehicle: "van", delivery_window: null,
        delivery_note_ref: "DN-WO-0001-01", manifest_ref: "MF-WO-0001-01",
        site_notified_at: "2026-09-01T00:00:00Z",
      },
    },
  ],
};

const MANIFEST = {
  data: {
    work_order: "WO-0001-01", status: "staged", project_code: "PRJ-0001",
    client_name: "Acme", item_name: "Lobby panels", station_name: null,
    qty: { ordered: 10, done: 10 }, manifest_ref: "MF-WO-0001-01",
    delivery_note_ref: "DN-WO-0001-01",
    packing: {
      type: "pallet", protection_spec: "edge guards", moisture_barrier_ref: "VCI/poly barrier",
      labels: [], handling: [],
    },
    dispatch: {
      vehicle: "van", delivery_window: null, manifest_ref: "MF-WO-0001-01",
      delivery_note_ref: "DN-WO-0001-01",
    },
    lines: [{ product_id: "pr1", sku: "SKU-A", description: "Panel A", qty: 10, uom: "pcs" }],
  },
};

function stubFetch() {
  const mock = vi.fn(async (url: string) => {
    const u = String(url);
    if (u.includes("/production/work-orders/w1/manifest")) return okJson(MANIFEST);
    if (u.includes("/production/dispatch")) return okJson(BOARD);
    return okJson({ data: [] });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

function renderSection() {
  return render(
    <MemoryRouter>
      <DispatchSection canWrite canManage />
    </MemoryRouter>,
  );
}

describe("DispatchSection", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("lists the dispatch board with the suggested vehicle", async () => {
    stubFetch();
    renderSection();
    await waitFor(() => expect(screen.getByText("WO-0001-01")).toBeInTheDocument());
    expect(screen.getByText("Lobby panels")).toBeInTheDocument();
    expect(screen.getByText("van")).toBeInTheDocument();
  });

  it("opens the generated manifest", async () => {
    stubFetch();
    renderSection();
    await waitFor(() => expect(screen.getByText("WO-0001-01")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Manifest" }));
    await waitFor(() =>
      expect(screen.getByText(/Manifest MF-WO-0001-01/)).toBeInTheDocument());
    expect(screen.getByText("Panel A")).toBeInTheDocument();
    expect(screen.getByText(/DN-WO-0001-01/)).toBeInTheDocument();
  });
});
