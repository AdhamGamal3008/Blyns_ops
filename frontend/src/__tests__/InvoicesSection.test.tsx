// Invoice lifecycle contract (docs/modules/FINANCE.md §2/§6): a draft has no
// number and can be sent; a posted invoice can only be paid or voided; a void
// must state a reason.

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InvoicesSection } from "../client/finance/InvoicesSection";

// Invoices are export-only, so `exportOnly` suppresses Import regardless; the
// grant just governs whether the Export button shows.
const CSV = { canExport: true, canImport: false, canApprove: false };

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

const INVOICES = {
  data: [
    {
      id: "i1", number: null, customer_ref: { name: "Draft Co" },
      issue_date: "2026-07-01T00:00:00Z", due_date: "2026-08-01T00:00:00Z",
      lines: [], subtotal: 100, tax_total: 0, total: 100, paid_amount: 0,
      status: "draft", currency: "USD",
    },
    {
      id: "i2", number: "INV-0001", customer_ref: { name: "Sent Co" },
      issue_date: "2026-07-01T00:00:00Z", due_date: "2026-08-01T00:00:00Z",
      lines: [], subtotal: 500, tax_total: 0, total: 500, paid_amount: 200,
      status: "partly_paid", currency: "USD",
    },
    {
      id: "i3", number: "INV-0002", customer_ref: { name: "Void Co" },
      issue_date: "2026-07-01T00:00:00Z", due_date: "2026-08-01T00:00:00Z",
      lines: [], subtotal: 900, tax_total: 0, total: 900, paid_amount: 0,
      status: "void", currency: "USD",
    },
  ],
};

function stubFetch() {
  const mock = vi.fn(async (url: string, _init?: RequestInit) => {
    if (String(url).includes("/finance/invoices")) return okJson(INVOICES);
    return okJson({ data: {} });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

const postCall = (mock: ReturnType<typeof stubFetch>) =>
  mock.mock.calls.find(([, init]) => init?.method === "POST");

describe("InvoicesSection", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("shows a draft with no number and its outstanding balance", async () => {
    stubFetch();
    render(<InvoicesSection canWrite={true} csv={CSV} />);
    await waitFor(() => expect(screen.getByText("Draft Co")).toBeInTheDocument());

    const rows = [...document.querySelectorAll("tbody tr")].map((r) =>
      [...r.querySelectorAll("td")].map((td) => td.textContent!.trim()));
    // draft: no number; partly_paid: 500 - 200 outstanding
    expect(rows[0][0]).toBe("—");
    expect(rows[1][0]).toBe("INV-0001");
    expect(rows[1][4]).toBe("$300.00");
  });

  it("offers Send only on a draft, and pay/void only on a posted invoice", async () => {
    stubFetch();
    render(<InvoicesSection canWrite={true} csv={CSV} />);
    await waitFor(() => expect(screen.getByText("Draft Co")).toBeInTheDocument());

    const rows = [...document.querySelectorAll("tbody tr")];
    const actions = (i: number) =>
      [...rows[i].querySelectorAll("button")].map((b) => b.textContent!.trim());

    expect(actions(0)).toEqual(["Send"]);                     // draft
    expect(actions(1)).toEqual(["Record payment", "Void"]);   // partly_paid
    expect(actions(2)).toEqual([]);                           // void — terminal
  });

  it("sending a draft posts to the send endpoint", async () => {
    const mock = stubFetch();
    render(<InvoicesSection canWrite={true} csv={CSV} />);
    await waitFor(() => expect(screen.getByText("Draft Co")).toBeInTheDocument());

    fireEvent.click(screen.getByText("Send"));
    await waitFor(() => {
      const post = postCall(mock);
      expect(post).toBeTruthy();
      expect(String(post![0])).toContain("/finance/invoices/i1/send");
    });
  });

  it("voiding requires a reason before it will submit", async () => {
    const mock = stubFetch();
    render(<InvoicesSection canWrite={true} csv={CSV} />);
    await waitFor(() => expect(screen.getByText("Sent Co")).toBeInTheDocument());

    fireEvent.click(screen.getByText("Void"));
    await waitFor(() =>
      expect(screen.getByText("Void invoice")).toBeInTheDocument());
    // nothing posted yet, and the reason field is required
    expect(postCall(mock)).toBeUndefined();
    const reason = document.querySelector('input[placeholder*="duplicate"]')!;
    expect((reason as HTMLInputElement).required).toBe(true);

    fireEvent.change(reason, { target: { value: "issued twice" } });
    fireEvent.click(screen.getByText("Void invoice"));
    await waitFor(() => {
      const post = postCall(mock);
      expect(String(post![0])).toContain("/finance/invoices/i2/void");
      expect(JSON.parse(String(post![1]!.body))).toEqual({ reason: "issued twice" });
    });
  });

  it("a payment defaults to the outstanding amount, not the total", async () => {
    const mock = stubFetch();
    render(<InvoicesSection canWrite={true} csv={CSV} />);
    await waitFor(() => expect(screen.getByText("Sent Co")).toBeInTheDocument());

    fireEvent.click(screen.getByText("Record payment"));
    await waitFor(() =>
      expect(screen.getByText(/\$300\.00 outstanding/)).toBeInTheDocument());

    const amount = document.querySelector('input[type="number"]') as HTMLInputElement;
    expect(amount.value).toBe("300");

    // the row button and the dialog's submit share a label; scope to the dialog
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Record payment" }));
    await waitFor(() => {
      const post = postCall(mock);
      expect(String(post![0])).toContain("/finance/payments");
      expect(JSON.parse(String(post![1]!.body))).toEqual({
        type: "customer_payment", ref_doc_type: "invoice",
        ref_doc_id: "i2", amount: 300, method: "bank",
      });
    });
  });

  it("read-only users get no posting controls", async () => {
    stubFetch();
    render(<InvoicesSection canWrite={false} csv={CSV} />);
    await waitFor(() => expect(screen.getByText("Draft Co")).toBeInTheDocument());
    expect(screen.queryByText("New invoice")).not.toBeInTheDocument();
    expect(screen.queryByText("Send")).not.toBeInTheDocument();
    expect(screen.queryByText("Void")).not.toBeInTheDocument();
  });
});
