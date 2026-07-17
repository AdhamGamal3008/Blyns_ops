// Vendor bills (AP) — the mirror of invoices (§1).

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import { Badge, Button, Card, ErrorNote, Field, Spinner } from "../../shared/ui";
import { STATUS_TONE, money, type Bill } from "./types";

export function BillsSection(props: { canWrite: boolean }) {
  const [bills, setBills] = useState<Bill[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    setError(null);
    api<Bill[]>("/finance/bills?page_size=100")
      .then((r) => setBills(r.data)).catch(setError);
  }, []);

  useEffect(load, [load]);

  async function send(bill: Bill) {
    setError(null);
    try {
      await api(`/finance/bills/${bill.id}/send`, { method: "POST" });
      load();
    } catch (err) {
      setError(err);
    }
  }

  async function pay(bill: Bill) {
    setError(null);
    try {
      await api("/finance/payments", {
        method: "POST",
        body: {
          type: "vendor_payment", ref_doc_type: "bill", ref_doc_id: bill.id,
          amount: bill.total - (bill.paid_amount ?? 0), method: "bank",
        },
      });
      load();
    } catch (err) {
      setError(err);
    }
  }

  if (!bills) return <Spinner />;

  return (
    <>
      <Card
        title={`Bills (${bills.length})`}
        actions={props.canWrite && (
          <Button onClick={() => setCreating(true)}>New bill</Button>
        )}
      >
        <ErrorNote error={error} />
        <table className="table">
          <thead>
            <tr>
              <th>Number</th><th>Vendor</th><th>Due</th>
              <th style={{ textAlign: "right" }}>Total</th>
              <th style={{ textAlign: "right" }}>Outstanding</th>
              <th>Status</th>
              {props.canWrite && <th></th>}
            </tr>
          </thead>
          <tbody>
            {bills.map((b) => {
              const outstanding = b.total - (b.paid_amount ?? 0);
              return (
                <tr key={b.id}>
                  <td className="muted">{b.number ?? "—"}</td>
                  <td><b>{b.vendor_ref?.name}</b></td>
                  <td className="muted">
                    {new Date(b.due_date).toLocaleDateString()}
                  </td>
                  <td style={{ textAlign: "right" }}>{money(b.total, b.currency)}</td>
                  <td style={{ textAlign: "right" }}>
                    <b className={outstanding > 0 ? "qty-out" : "qty-in"}>
                      {money(outstanding, b.currency)}
                    </b>
                  </td>
                  <td>
                    <Badge tone={STATUS_TONE[b.status] ?? "neutral"}>{b.status}</Badge>
                  </td>
                  {props.canWrite && (
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      {b.status === "draft" && (
                        <Button variant="ghost" onClick={() => send(b)}>Post</Button>
                      )}
                      {(b.status === "sent" || b.status === "partly_paid") && (
                        <Button variant="ghost" onClick={() => pay(b)}>Pay in full</Button>
                      )}
                    </td>
                  )}
                </tr>
              );
            })}
            {bills.length === 0 && (
              <tr><td colSpan={7} className="muted">No bills yet.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
      {creating && (
        <BillModal onDone={(ok) => { setCreating(false); if (ok) load(); }} />
      )}
    </>
  );
}

function BillModal(props: { onDone: (ok: boolean) => void }) {
  const [vendor, setVendor] = useState("");
  const [due, setDue] = useState("");
  const [description, setDescription] = useState("");
  const [qty, setQty] = useState("1");
  const [unitPrice, setUnitPrice] = useState("0");
  const [taxRate, setTaxRate] = useState("0");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/finance/bills", {
        method: "POST",
        body: {
          vendor_ref: { name: vendor },
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
        <h3 style={{ marginBottom: 16 }}>New bill</h3>
        <ErrorNote error={error} />
        <form onSubmit={submit}>
          <Field label="Vendor">
            <input value={vendor} onChange={(e) => setVendor(e.target.value)} required />
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
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
            <Button variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save draft"}</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
