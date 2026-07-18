// Versioned deliverables (§3.7, acceptance #6): every revision is appended and
// nothing is overwritten — the UI only ever adds. A `bom` deliverable carries
// product lines that Stage 8 reserves through Inventory.

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import { Badge, Button, Card, ErrorNote, Field, Spinner } from "../../shared/ui";
import { humanize, type Deliverable, type DeliverableKind } from "./types";

const KINDS: DeliverableKind[] = [
  "shop_drawing", "bom", "scan", "photo", "report", "certificate",
];

export function DeliverablesSection(props: {
  projectId: string; canWrite: boolean; onChanged: () => void;
}) {
  const [items, setItems] = useState<Deliverable[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);
  const [revising, setRevising] = useState<Deliverable | null>(null);

  const load = useCallback(() => {
    setError(null);
    api<Deliverable[]>(`/projects/${props.projectId}/deliverables?page_size=100`)
      .then((r) => setItems(r.data)).catch(setError);
  }, [props.projectId]);

  useEffect(load, [load]);

  if (!items) return <Spinner />;

  return (
    <>
      <Card
        title={`Deliverables (${items.length})`}
        actions={props.canWrite && (
          <Button onClick={() => setCreating(true)}>New deliverable</Button>
        )}
      >
        <ErrorNote error={error} />
        <table className="table">
          <thead>
            <tr>
              <th>Title</th><th>Kind</th><th>Stage</th><th>Version</th>
              {props.canWrite && <th></th>}
            </tr>
          </thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.id}>
                <td><b>{d.title}</b></td>
                <td><Badge tone="neutral">{humanize(d.kind)}</Badge></td>
                <td className="muted">{humanize(d.stage_key)}</td>
                <td className="muted">
                  v{d.current_version}
                  {d.kind === "bom" && d.lines?.length ? ` · ${d.lines.length} line(s)` : ""}
                </td>
                {props.canWrite && (
                  <td style={{ textAlign: "right" }}>
                    <Button variant="ghost" onClick={() => setRevising(d)}>Add revision</Button>
                  </td>
                )}
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={props.canWrite ? 5 : 4} className="muted">
                No deliverables yet.
              </td></tr>
            )}
          </tbody>
        </table>
      </Card>
      {creating && (
        <DeliverableModal projectId={props.projectId}
          onDone={(ok) => { setCreating(false); if (ok) { load(); props.onChanged(); } }} />
      )}
      {revising && (
        <RevisionModal projectId={props.projectId} deliverable={revising}
          onDone={(ok) => { setRevising(null); if (ok) load(); }} />
      )}
    </>
  );
}

function DeliverableModal(props: { projectId: string; onDone: (ok: boolean) => void }) {
  const [kind, setKind] = useState<DeliverableKind>("shop_drawing");
  const [title, setTitle] = useState("");
  const [fileRef, setFileRef] = useState("");
  const [lines, setLines] = useState<{ product_id: string; qty: string }[]>(
    [{ product_id: "", qty: "" }]);
  const [products, setProducts] = useState<{ id: string; name: string; sku: string }[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<{ id: string; name: string; sku: string }[]>("/inventory/products?page_size=100")
      .then((r) => setProducts(r.data)).catch(() => setProducts([]));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        kind, title, file_ref: fileRef || `vault://${title}`,
      };
      if (kind === "bom") {
        body.lines = lines
          .filter((l) => l.product_id && l.qty)
          .map((l) => ({ product_id: l.product_id, qty: Number(l.qty) }));
      }
      await api(`/projects/${props.projectId}/deliverables`, { method: "POST", body });
      props.onDone(true);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={() => props.onDone(false)}>
      <div className="modal card" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 14 }}>New deliverable</h3>
        <ErrorNote error={error} />
        <form onSubmit={submit}>
          <Field label="Kind">
            <select value={kind} onChange={(e) => setKind(e.target.value as DeliverableKind)}>
              {KINDS.map((k) => <option key={k} value={k}>{humanize(k)}</option>)}
            </select>
          </Field>
          <Field label="Title">
            <input value={title} onChange={(e) => setTitle(e.target.value)} required />
          </Field>
          <Field label="File reference">
            <input value={fileRef} onChange={(e) => setFileRef(e.target.value)}
              placeholder="vault://… (optional)" />
          </Field>
          {kind === "bom" && (
            <div>
              <div className="kpi-label" style={{ fontSize: 11, marginBottom: 4 }}>
                BOM lines (reserved from Inventory at Stage 8)
              </div>
              {lines.map((l, i) => (
                <div key={i} style={{ display: "flex", gap: 8 }}>
                  <Field label="Product">
                    <select value={l.product_id} onChange={(e) => {
                      const next = [...lines]; next[i] = { ...l, product_id: e.target.value };
                      setLines(next);
                    }}>
                      <option value="">— select —</option>
                      {products.map((p) => (
                        <option key={p.id} value={p.id}>{p.sku} · {p.name}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Qty">
                    <input type="number" step="any" min="0" value={l.qty} onChange={(e) => {
                      const next = [...lines]; next[i] = { ...l, qty: e.target.value };
                      setLines(next);
                    }} />
                  </Field>
                </div>
              ))}
              <Button variant="ghost"
                onClick={() => setLines([...lines, { product_id: "", qty: "" }])}>
                + Add line
              </Button>
            </div>
          )}
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
            <Button variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Create"}</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function RevisionModal(props: {
  projectId: string; deliverable: Deliverable; onDone: (ok: boolean) => void;
}) {
  const [fileRef, setFileRef] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api(`/projects/${props.projectId}/deliverables/${props.deliverable.id}/revisions`, {
        method: "POST", body: { file_ref: fileRef || `vault://rev`, note },
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
          Revise {props.deliverable.title} → v{props.deliverable.current_version + 1}
        </h3>
        <p className="muted" style={{ marginBottom: 14, fontSize: 13 }}>
          Every version is kept — this appends, it never overwrites.
        </p>
        <ErrorNote error={error} />
        <form onSubmit={submit}>
          <Field label="New file reference">
            <input value={fileRef} onChange={(e) => setFileRef(e.target.value)}
              placeholder="vault://…" />
          </Field>
          <Field label="Note">
            <input value={note} onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. clash fix" />
          </Field>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
            <Button variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Add revision"}</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
