// Pipeline board (§3 `/crm/pipeline`): stage buckets with counts + summed
// amounts, and the deal list underneath. Stage moves go through
// PATCH /crm/deals/{id}/stage so the `lost_reason` rule is enforced server-side.

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import { Badge, Button, Card, ErrorNote, Field, Spinner } from "../../shared/legacy-ui";

interface StageBucket {
  stage: string;
  count: number;
  amount: number;
  is_terminal: boolean;
}

interface Pipeline {
  pipeline: string;
  name: string;
  stages: StageBucket[];
  open_value: number;
}

interface Deal {
  id: string;
  title: string;
  stage: string;
  amount: number;
  currency: string;
  expected_close_date?: string | null;
  lost_reason?: string | null;
}

export function money(n: number, currency = "USD"): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency", currency, maximumFractionDigits: 0,
  }).format(n);
}

export function PipelineBoard(props: { canWrite: boolean }) {
  const [pipeline, setPipeline] = useState<Pipeline | null>(null);
  const [deals, setDeals] = useState<Deal[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [moving, setMoving] = useState<Deal | null>(null);
  const [creating, setCreating] = useState(false);

  // scope the cards to the same pipeline the buckets count, so a column's
  // total can never disagree with the cards under it
  const load = useCallback(() => {
    api<Pipeline>("/crm/pipeline").then((r) => setPipeline(r.data)).catch(setError);
    api<Deal[]>("/crm/deals?page_size=100&pipeline=default")
      .then((r) => setDeals(r.data)).catch(setError);
  }, []);

  useEffect(load, [load]);

  async function move(deal: Deal, stage: string) {
    // `lost` needs a reason — collect it before calling (acceptance #2).
    if (stage === "lost") {
      setMoving(deal);
      return;
    }
    setError(null);
    try {
      await api(`/crm/deals/${deal.id}/stage`, { method: "PATCH", body: { stage } });
      load();
    } catch (err) {
      setError(err);
    }
  }

  if (!pipeline || !deals) return <Spinner />;

  return (
    <>
      <Card
        title={`Pipeline — ${money(pipeline.open_value)} open`}
        actions={props.canWrite && (
          <Button onClick={() => setCreating(true)}>New deal</Button>
        )}
      >
        <ErrorNote error={error} />
        <div className="pipe-board">
          {pipeline.stages.map((s) => (
            <div key={s.stage} className={`pipe-col ${s.is_terminal ? "terminal" : ""}`}>
              <div className="pipe-col-head">
                <b>{s.stage}</b>
                <span className="muted">{s.count}</span>
              </div>
              <div className="pipe-col-total">{money(s.amount)}</div>
              {deals.filter((d) => d.stage === s.stage).map((d) => (
                <div key={d.id} className="pipe-card" title={d.lost_reason ?? ""}>
                  <div className="pipe-card-title">{d.title}</div>
                  <div className="muted">{money(d.amount, d.currency)}</div>
                  {props.canWrite && !s.is_terminal && (
                    <select value={d.stage} className="pipe-move"
                      onChange={(e) => move(d, e.target.value)}>
                      {pipeline.stages.map((o) => (
                        <option key={o.stage} value={o.stage}>{o.stage}</option>
                      ))}
                    </select>
                  )}
                  {s.is_terminal && <Badge tone={s.stage === "won" ? "ok" : "danger"}>
                    {s.stage}
                  </Badge>}
                </div>
              ))}
            </div>
          ))}
        </div>
      </Card>
      {moving && (
        <LostReasonModal deal={moving}
          onDone={(ok) => { setMoving(null); if (ok) load(); }} />
      )}
      {creating && (
        <DealModal onDone={(ok) => { setCreating(false); if (ok) load(); }} />
      )}
    </>
  );
}

function LostReasonModal(props: { deal: Deal; onDone: (ok: boolean) => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api(`/crm/deals/${props.deal.id}/stage`, {
        method: "PATCH", body: { stage: "lost", lost_reason: reason },
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
        <h3 style={{ marginBottom: 16 }}>Mark “{props.deal.title}” lost</h3>
        <ErrorNote error={error} />
        <form onSubmit={submit}>
          <Field label="Reason (required)">
            <input value={reason} onChange={(e) => setReason(e.target.value)}
              required placeholder="e.g. price, timing, competitor" />
          </Field>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
            <Button variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
            <Button type="submit" variant="danger" disabled={busy}>
              {busy ? "Saving…" : "Mark lost"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function DealModal(props: { onDone: (ok: boolean) => void }) {
  const [title, setTitle] = useState("");
  const [amount, setAmount] = useState("0");
  const [close, setClose] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/crm/deals", {
        method: "POST",
        body: {
          title, amount: Number(amount),
          expected_close_date: close ? new Date(close).toISOString() : null,
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
        <h3 style={{ marginBottom: 16 }}>New deal</h3>
        <ErrorNote error={error} />
        <form onSubmit={submit}>
          <Field label="Title">
            <input value={title} onChange={(e) => setTitle(e.target.value)} required />
          </Field>
          <Field label="Amount">
            <input type="number" min="0" value={amount}
              onChange={(e) => setAmount(e.target.value)} />
          </Field>
          <Field label="Expected close date">
            <input type="date" value={close} onChange={(e) => setClose(e.target.value)} />
          </Field>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
            <Button variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Create deal"}</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
