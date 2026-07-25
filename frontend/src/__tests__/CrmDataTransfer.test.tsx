// CRM CSV import/export UI (docs/modules/CRM.md §7). The properties that
// matter: the column picker is built from the server's field list and its
// selection reaches the request; and nothing is written until the user has
// seen a report of what the file would do.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DataTransfer } from "../shared/csv/DataTransfer";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

const META = {
  data: {
    entity: "deals",
    label: "Deals",
    importable: true,
    append_only: false,
    fields: [
      { key: "title", header: "Title", kind: "str", required: true, choices: [],
        importable: true, exportable: true, example: "Globex rollout", hint: "" },
      { key: "account_name", header: "Account", kind: "str", required: false,
        choices: [], importable: true, exportable: true, example: "Globex Corp",
        hint: "Must already exist — import Accounts first." },
      { key: "stage", header: "Stage", kind: "enum", required: false,
        choices: ["new", "won", "lost"], importable: true, exportable: true,
        example: "new", hint: "" },
      { key: "amount", header: "Amount", kind: "float", required: false, choices: [],
        importable: true, exportable: true, example: "25000", hint: "" },
      { key: "id", header: "Record ID", kind: "str", required: false, choices: [],
        importable: false, exportable: true, example: "", hint: "" },
    ],
    filters: {
      status: { label: "Stage", choices: ["new", "won", "lost"] },
      date_fields: [
        { key: "created_at", label: "Created at" },
        { key: "expected_close_date", label: "Expected close date" },
      ],
      supports_search: true,
      supports_owner: true,
    },
  },
};

const VALIDATED = {
  data: {
    entity: "deals", label: "Deals", mode: "validate", file: "deals.csv",
    rows: 3, created: 1, updated: 1, failed: 1,
    columns: ["title", "stage"], ignored_columns: ["Notes"],
    errors: [{
      row: 4, column: "Stage", value: "smouldering",
      message: "“smouldering” is not one of: new, won, lost",
    }],
    errors_truncated: false,
  },
};

const COMMITTED = {
  data: { ...VALIDATED.data, mode: "commit", created: 1, updated: 1, failed: 1 },
};

function stubFetch() {
  const mock = vi.fn(async (url: string, init?: RequestInit) => {
    const u = String(url);
    if (u.includes("/export/deals/fields")) return okJson(META);
    if (u.includes("/import/deals") && init?.method === "POST") {
      return okJson(u.includes("mode=commit") ? COMMITTED : VALIDATED);
    }
    if (u.includes("/export/deals") || u.includes("/template")) {
      return new Response("Title\r\n", {
        status: 200, headers: { "Content-Type": "text/csv" },
      });
    }
    return okJson({ data: {} });
  });
  vi.stubGlobal("fetch", mock);
  // apiDownload saves through an object URL, which jsdom does not implement.
  vi.stubGlobal("URL", Object.assign(URL, {
    createObjectURL: vi.fn(() => "blob:stub"),
    revokeObjectURL: vi.fn(),
  }));
  return mock;
}

/** The export request the dialog fired, if any. */
function exportCall(mock: ReturnType<typeof stubFetch>) {
  return mock.mock.calls.find(
    ([url, init]) =>
      String(url).includes("/crm/export/deals?") && init?.method === undefined,
  );
}

function csvFile(text = "Title,Stage\r\nAlpha,new\r\n") {
  return new File([text], "deals.csv", { type: "text/csv" });
}

describe("CRM DataTransfer", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("read-only users can export but are not offered import", async () => {
    stubFetch();
    render(<DataTransfer module="crm" entity="deals" canWrite={false} onImported={() => {}} />);
    expect(screen.getByRole("button", { name: "Export" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Import" })).not.toBeInTheDocument();
  });

  it("builds the column picker from the server's field list", async () => {
    stubFetch();
    render(<DataTransfer module="crm" entity="deals" canWrite onImported={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Export" }));

    await waitFor(() => expect(screen.getByRole("checkbox", { name: "Title" })).toBeInTheDocument());
    // every exportable column is offered, ticked to begin with
    for (const header of ["Title", "Account", "Stage", "Amount", "Record ID"]) {
      expect(screen.getByRole("checkbox", { name: header })).toBeInTheDocument();
    }
    expect(screen.getByText("5 of 5 selected")).toBeInTheDocument();
  });

  it("sends only the ticked columns, plus the chosen filters", async () => {
    const mock = stubFetch();
    render(<DataTransfer module="crm" entity="deals" canWrite onImported={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() => expect(screen.getByRole("checkbox", { name: "Title" })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("checkbox", { name: "Account" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Record ID" }));
    fireEvent.change(screen.getByLabelText("Stage", { selector: "select" }), {
      target: { value: "won" },
    });
    fireEvent.change(screen.getByLabelText("Owner"), { target: { value: "mine" } });
    fireEvent.change(screen.getByLabelText("Date column"), {
      target: { value: "expected_close_date" },
    });
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-01-01" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-03-31" } });

    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));

    await waitFor(() => expect(exportCall(mock)).toBeTruthy());
    const url = new URL(`http://x${String(exportCall(mock)![0]).split("/api/v1")[1]}`);
    // spec order is preserved, and the two unticked columns are gone
    expect(url.searchParams.get("fields")).toBe("title,stage,amount");
    expect(url.searchParams.get("status")).toBe("won");
    expect(url.searchParams.get("owner")).toBe("mine");
    expect(url.searchParams.get("date_field")).toBe("expected_close_date");
    expect(url.searchParams.get("date_from")).toBe("2026-01-01");
    expect(url.searchParams.get("date_to")).toBe("2026-03-31");
  });

  it("cannot export with nothing selected", async () => {
    stubFetch();
    render(<DataTransfer module="crm" entity="deals" canWrite onImported={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() => expect(screen.getByRole("checkbox", { name: "Title" })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    await waitFor(() =>
      expect(screen.getByText("0 of 5 selected")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Export CSV" })).toBeDisabled();
  });

  it("checks an uploaded file before writing anything, then commits on confirm", async () => {
    const mock = stubFetch();
    const onImported = vi.fn();
    render(<DataTransfer module="crm" entity="deals" canWrite onImported={onImported} />);
    fireEvent.click(screen.getByRole("button", { name: "Import" }));

    await waitFor(() =>
      expect(screen.getByText("1. Start from the template")).toBeInTheDocument());

    const input = document.querySelector('input[type="file"]')!;
    fireEvent.change(input, { target: { files: [csvFile()] } });

    // the first request is a dry run — nothing is written yet
    await waitFor(() => expect(screen.getByText("1 to create")).toBeInTheDocument());
    const posts = mock.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(posts).toHaveLength(1);
    expect(String(posts[0][0])).toContain("mode=validate");
    expect(onImported).not.toHaveBeenCalled();

    // the report names what will happen and what will be skipped
    expect(screen.getByText("1 to update")).toBeInTheDocument();
    expect(screen.getByText("1 with problems")).toBeInTheDocument();
    expect(screen.getByText(/smouldering.*is not one of/)).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();          // the failing row
    expect(screen.getByText(/Notes/)).toBeInTheDocument();      // ignored column

    fireEvent.click(screen.getByRole("button", { name: "Import 2 rows" }));

    await waitFor(() => expect(onImported).toHaveBeenCalled());
    const commit = mock.mock.calls.filter(
      ([url, init]) => init?.method === "POST" && String(url).includes("mode=commit"),
    );
    expect(commit).toHaveLength(1);
    expect(screen.getByText(/1 created, 1 updated, 1 skipped/)).toBeInTheDocument();
  });

  it("will not commit a file whose every row failed", async () => {
    const mock = vi.fn(async (url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes("/export/deals/fields")) return okJson(META);
      if (u.includes("/import/deals") && init?.method === "POST") {
        return okJson({
          data: { ...VALIDATED.data, created: 0, updated: 0, failed: 3 },
        });
      }
      return okJson({ data: {} });
    });
    vi.stubGlobal("fetch", mock);

    render(<DataTransfer module="crm" entity="deals" canWrite onImported={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Import" }));
    await waitFor(() =>
      expect(screen.getByText("1. Start from the template")).toBeInTheDocument());

    fireEvent.change(document.querySelector('input[type="file"]')!, {
      target: { files: [csvFile()] },
    });

    await waitFor(() => expect(screen.getByText("3 with problems")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Import 0 rows" })).toBeDisabled();
  });

  it("offers the template with an example row by default", async () => {
    const mock = stubFetch();
    render(<DataTransfer module="crm" entity="deals" canWrite onImported={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Import" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Download template" })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Download template" }));
    await waitFor(() =>
      expect(
        mock.mock.calls.some(([url]) =>
          String(url).includes("/crm/import/deals/template?sample=true")),
      ).toBe(true));
  });
});
