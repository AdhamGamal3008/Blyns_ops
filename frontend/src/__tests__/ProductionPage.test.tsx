// Production shell (docs/PRODUCTION_MODULE_PLAN.md §7): the five work-centre tabs,
// with the Queue as the default landing view rendering the cross-project work list.

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProductionPage } from "../client/production/ProductionPage";
import type { ClientMe } from "../shared/types";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

function me(level = 3): ClientMe {
  return {
    id: "u1", email: "o@acme.com", name: "Owner", must_reset_password: false,
    company: { slug: "acme", name: "Acme", enabled_modules: ["production"] },
    role: { id: "r1", name: "Owner", permissions: { production: level } as never },
  };
}

const QUEUE = {
  data: [
    {
      id: "w1", code: "WO-0001-01", project_id: "p1", project_code: "PRJ-0001",
      client_name: "Acme", item_name: "Lobby panels", bom_lines: [],
      qty: { ordered: 42, done: 0 }, station_route: [], current_station_id: null,
      station_name: null, due_date: "2026-08-20T00:00:00Z", status: "queued",
      revision_conflict: false,
    },
  ],
};

function stubFetch() {
  const mock = vi.fn(async (url: string) => {
    const u = String(url);
    if (u.includes("/production/context")) return okJson({ data: { can_manage: true } });
    if (u.includes("/production/queue")) return okJson(QUEUE);
    if (u.includes("/production/work-orders")) return okJson({ ...QUEUE, meta: { total: 1 } });
    if (u.includes("/projects")) return okJson({ data: [] });
    return okJson({ data: [] });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

function renderPage(level = 3) {
  return render(
    <MemoryRouter initialEntries={["/app/production"]}>
      <Routes>
        <Route element={<Outlet context={me(level)} />}>
          <Route path="/app/production" element={<ProductionPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProductionPage", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("renders the five work-centre tabs", async () => {
    stubFetch();
    renderPage();
    for (const label of ["Queue", "Work Orders", "Quality", "Stations", "Dispatch"]) {
      expect(screen.getByRole("tab", { name: label })).toBeInTheDocument();
    }
    await waitFor(() => expect(screen.getByText("WO-0001-01")).toBeInTheDocument());
  });

  it("lands on the Queue and lists the cross-project work orders", async () => {
    stubFetch();
    renderPage();
    await waitFor(() => expect(screen.getByText("WO-0001-01")).toBeInTheDocument());
    expect(screen.getByText("Lobby panels")).toBeInTheDocument();
  });
});
