// Job-cost capture (§3.9, acceptance #7): labor/material actuals post a balanced
// Dr COGS / Cr AP entry to Finance and roll into the project budget. A material
// actual also draws down the Stage-8 commitment, so a posted cost refreshes the
// parent budget header.

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import { Badge, Button, Card, ErrorNote, Field, Spinner } from "../../shared/ui";
import { humanize, money, type JobCost } from "./types";

const COST_TYPES: JobCost["cost_type"][] = ["labor", "material", "subcontractor", "machine"];

export function JobCostsSection(props: {
  projectId: string; canWrite: boolean; currency: string; onChanged: () => void;
}) {
  const [items, setItems] = useState<JobCost[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    setError(null);
    api<JobCost[]>(`/projects/${props.projectId}/job-costs?page_size=100`)
      .then((r) => setItems(r.data)).catch(setError);
  }, [props.projectId]);

  useEffect(load, [load]);

  if (!items) return <Spinner />;

  const total = items.reduce((s, c) => s + c.amount, 0);

  return (
    <>
      <Card
        title={`Job costs (${money(total, props.currency)})`}
        actions={props.canWrite && (
          <Button onClick={() => setCreating(true)}>Add cost</Button>
        )}
      >
        <ErrorNote error={error} />
        <table className="table">
          <thead>
            <tr>
              <th>Type</th><th>Description</th><th>Stage</th>
              <th style={{ textAlign: "right" }}>Amount</th><th>Posted</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr key={c.id}>
                <td><Badge tone="neutral">{c.cost_type}</Badge></td>
                <td>{c.description || <span className="muted">—</span>}</td>
                <td className="muted">{humanize(c.stage_key)}</td>
                <td style={{ textAlign: "right" }}>{money(c.amount, props.currency)}</td>
                <td>
                  {c.posted_to_finance_ref
                    ? <Badge tone="ok">ledger</Badge>
                    : <span className="muted">—</span>}
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={5} className="muted">No costs captured yet.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
      {creating && (
        <CostModal projectId={props.projectId}
          onDone={(ok) => { setCreating(false); if (ok) { load(); props.onChanged(); } }} />
      )}
    </>
  );
}

function CostModal(props: { projectId: string; onDone: (ok: boolean) => void }) {
  const [costType, setCostType] = useState<JobCost["cost_type"]>("labor");
  const [description, setDescription] = useState("");
  const [hours, setHours] = useState("");
  const [quantity, setQuantity] = useState("");
  const [unitCost, setUnitCost] = useState("");
  const [post, setPost] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const isLabor = costType === "labor";
  const measure = Number(isLabor ? hours : quantity) || 0;
  const amount = measure * (Number(unitCost) || 0);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api(`/projects/${props.projectId}/job-costs`, {
        method: "POST",
        body: {
          cost_type: costType,
          description: description || null,
          hours: isLabor ? Number(hours) : 0,
          quantity: isLabor ? 0 : Number(quantity),
          unit_cost: Number(unitCost),
          post_to_finance: post,
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
        <h3 style={{ marginBottom: 14 }}>Add job cost</h3>
        <ErrorNote error={error} />
        <form onSubmit={submit}>
          <Field label="Cost type">
            <select value={costType}
              onChange={(e) => setCostType(e.target.value as JobCost["cost_type"])}>
              {COST_TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
            </select>
          </Field>
          <Field label="Description">
            <input value={description} onChange={(e) => setDescription(e.target.value)} />
          </Field>
          <Field label={isLabor ? "Hours" : "Quantity"}>
            <input type="number" step="any" min="0"
              value={isLabor ? hours : quantity}
              onChange={(e) => (isLabor ? setHours : setQuantity)(e.target.value)} required />
          </Field>
          <Field label="Unit cost">
            <input type="number" step="any" min="0" value={unitCost}
              onChange={(e) => setUnitCost(e.target.value)} required />
          </Field>
          <label style={{ display: "flex", gap: 8, alignItems: "center", margin: "4px 0 8px" }}>
            <input type="checkbox" style={{ width: "auto" }} checked={post}
              onChange={(e) => setPost(e.target.checked)} />
            <span style={{ fontSize: 13 }}>Post to Finance (Dr COGS / Cr AP)</span>
          </label>
          <p className="muted" style={{ fontSize: 13 }}>
            Amount <b>{money(amount)}</b>
          </p>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
            <Button variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
            <Button type="submit" disabled={busy || amount <= 0}>
              {busy ? "Posting…" : "Add cost"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
