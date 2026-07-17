// Invoices (§1/§2). A draft is editable and carries no number; sending claims
// the number and posts the journal entry; a posted invoice is only ever voided.

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import { Badge, Button, Card, ErrorNote, Field, Spinner } from "../../shared/ui";
import { STATUS_TONE, money, type Invoice } from "./types";

export function InvoicesSection(props: { canWrite: boolean; openNew?: boolean }) {
  const [invoices, setInvoices] = useState<Invoice[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(Boolean(props.openNew));
  const [paying, setPaying] = useState<Invoice | null>(null);
  const [voiding, setVoiding] = useState<Invoice | null>(null);

  const load = useCallback(() => {
    setError(null);
    api<Invoice[]>("/finance/invoices?page_size=100")
      .then((r) => setInvoices(r.data)).catch(setError);
  }, []);

  useEffect(load, [load]);

  async function send(inv: Invoice) {
    setError(null);
    try {
      await api(`/finance/invoices/${inv.id}/send`, { method: "POST" });
      load();
    } catch (err) {
      setError(err);
    }
  }

  if (!invoices) return <Spinner />;

  return (
    <>
      <Card
        title={`Invoices (${invoices.length})`}
        actions={props.canWrite && (
          <Button onClick={() => setCreating(true)}>New invoice</Button>
        )}
      >
        <ErrorNote error={error} />
        <table className="table">
          <thead>
            <tr>
              <th>Number</th><th>Customer</th><th>Due</th>
              <th style={{ textAlign: "right" }}>Total</th>
              <th style={{ textAlign: "right" }}>Outstanding</th>
              <th>Status</th>
              {props.canWrite && <th></th>}
            </tr>
          </thead>
          <tbody>
            {invoices.map((inv) => {
              const outstanding = inv.total - (inv.paid_amount ?? 0);
              return (
                <tr key={inv.id}>
                  <td className="muted">{inv.number ?? "—"}</td>
                  <td><b>{inv.customer_ref?.name}</b></td>
                  <td className="muted">
                    {new Date(inv.due_date).toLocaleDateString()}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {money(inv.total, inv.currency)}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {inv.status === "void"
                      ? <span className="muted">—</span>
                      : <b className={outstanding > 0 ? "qty-out" : "qty-in"}>
                          {money(outstanding, inv.currency)}
                        </b>}
                  </td>
                  <td>
                    <Badge tone={STATUS_TONE[inv.status] ?? "neutral"}>
                      {inv.status}
                    </Badge>
                  </td>
                  {props.canWrite && (
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      {inv.status === "draft" && (
                        <Button variant="ghost" onClick={() => send(inv)}>Send</Button>
                      )}
                      {(inv.status === "sent" || inv.status === "partly_paid") && (
                        <>
                          <Button variant="ghost" onClick={() => setPaying(inv)}>
                            Record payment
                          </Button>{" "}
                          <Button variant="ghost" onClick={() => setVoiding(inv)}>
                            Void
                          </Button>
                        </>
                      )}
                    </td>
                  )}
                </tr>
              );
            })}
            {invoices.length === 0 && (
              <tr><td colSpan={7} className="muted">No invoices yet.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
      {creating && (
        <InvoiceModal onDone={(ok) => { setCreating(false); if (ok) load(); }} />
      )}
      {paying && (
        <PaymentModal invoice={paying}
          onDone={(ok) => { setPaying(null); if (ok) load(); }} />
      )}
      {voiding && (
        <VoidModal invoice={voiding}
          onDone={(ok) => { setVoiding(null); if (ok) load(); }} />
      )}
    </>
  );
}

function InvoiceModal(props: { onDone: (ok: boolean) => void }) {
  const [customer, setCustomer] = useState("");
  const [due, setDue] = useState("");
  const [description, setDescription] = useState("");
  const [qty, setQty] = useState("1");
  const [unitPrice, setUnitPrice] = useState("0");
  const [taxRate, setTaxRate] = useState("0");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const subtotal = Number(qty) * Number(unitPrice);
  const tax = subtotal * Number(taxRate) / 100;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/finance/invoices", {
        method: "POST",
        body: {
          customer_ref: { name: customer },
          due_date: new Date(due).toISOString(),
          lines: [{
            description, qty: Number(qty),
            unit_price: Number(unitPrice), tax_rate: Number(taxRate),
          }],
        },
      });
      props.onDone(true);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={() => props.onDone(false)}>
      <div className="modal card" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 4 }}>New invoice</h3>
        <p className="muted" style={{ marginBottom: 16, fontSize: 13 }}>
          Saved as a draft — it gets its number when you send it.
        </p>
        <ErrorNote error={error} />
        <form onSubmit={submit}>
          <Field label="Customer">
            <input value={customer} onChange={(e) => setCustomer(e.target.value)}
              required />
          </Field>
          <Field label="Due date">
            <input type="date" value={due} onChange={(e) => setDue(e.target.value)}
              required />
          </Field>
          <Field label="Description">
            <input value={description} onChange={(e) => setDescription(e.target.value)}
              required />
          </Field>
          <Field label="Qty">
            <input type="number" step="any" min="0.0001" value={qty}
              onChange={(e) => setQty(e.target.value)} required />
          </Field>
          <Field label="Unit price">
            <input type="number" step="any" min="0" value={unitPrice}
              onChange={(e) => setUnitPrice(e.target.value)} required />
          </Field>
          <Field label="Tax rate (%)">
            <input type="number" step="any" min="0" max="100" value={taxRate}
              onChange={(e) => setTaxRate(e.target.value)} />
          </Field>
          <p className="muted" style={{ fontSize: 13 }}>
            Subtotal {money(subtotal)} · Tax {money(tax)} ·{" "}
            <b>Total {money(subtotal + tax)}</b>
          </p>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
            <Button variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Save draft"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function PaymentModal(props: {
  invoice: Invoice;
  onDone: (ok: boolean) => void;
}) {
  const outstanding = props.invoice.total - (props.invoice.paid_amount ?? 0);
  const [amount, setAmount] = useState(String(outstanding));
  const [method, setMethod] = useState("bank");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/finance/payments", {
        method: "POST",
        body: {
          type: "customer_payment", ref_doc_type: "invoice",
          ref_doc_id: props.invoice.id, amount: Number(amount), method,
        },
      });
      props.onDone(true);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={() => props.onDone(false)}>
      <div className="modal card" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 4 }}>
          Record payment — {props.invoice.number}
        </h3>
        <p className="muted" style={{ marginBottom: 16, fontSize: 13 }}>
          {money(outstanding, props.invoice.currency)} outstanding.
        </p>
        <ErrorNote error={error} />
        <form onSubmit={submit}>
          <Field label="Amount">
            <input type="number" step="0.01" min="0.01" max={outstanding}
              value={amount} onChange={(e) => setAmount(e.target.value)} required />
          </Field>
          <Field label="Method">
            <select value={method} onChange={(e) => setMethod(e.target.value)}>
              <option value="bank">Bank</option>
              <option value="cash">Cash</option>
              <option value="other">Other</option>
            </select>
          </Field>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
            <Button variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Posting…" : "Record payment"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function VoidModal(props: { invoice: Invoice; onDone: (ok: boolean) => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api(`/finance/invoices/${props.invoice.id}/void`, {
        method: "POST", body: { reason },
      });
      props.onDone(true);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={() => props.onDone(false)}>
      <div className="modal card" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 4 }}>Void {props.invoice.number}</h3>
        <p className="muted" style={{ marginBottom: 16, fontSize: 13 }}>
          The original entry stays in the ledger; voiding posts a reversing entry.
        </p>
        <ErrorNote error={error} />
        <form onSubmit={submit}>
          <Field label="Reason (required)">
            <input value={reason} onChange={(e) => setReason(e.target.value)}
              required placeholder="e.g. duplicate, issued in error" />
          </Field>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
            <Button variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
            <Button type="submit" variant="danger" disabled={busy}>
              {busy ? "Voiding…" : "Void invoice"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
