// Production Phase 3 UI (docs/PRODUCTION_MODULE_PLAN.md §6): the Stations view
// lists each work centre with its current load vs capacity.

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StationsSection } from "../client/production/StationsSection";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

const STATIONS = {
  data: [
    {
      id: "s1", code: "CUT", name: "Cutting / CNC", material_types: ["panel"],
      capacity_units_per_day: 40, is_active: true,
      load: { units: 30, work_orders: 2, capacity: 40, utilization: 75 },
    },
    {
      id: "s2", code: "QC", name: "QC Bench", material_types: [],
      capacity_units_per_day: 50, is_active: true,
      load: { units: 0, work_orders: 0, capacity: 50, utilization: 0 },
    },
  ],
};

describe("StationsSection", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("lists work centres with their load and utilization", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => okJson(STATIONS)));
    render(<StationsSection />);
    await waitFor(() =>
      expect(screen.getByText("Cutting / CNC")).toBeInTheDocument());
    expect(screen.getByText("QC Bench")).toBeInTheDocument();
    expect(screen.getByText("75%")).toBeInTheDocument();
  });
});
