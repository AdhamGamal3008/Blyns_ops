// Leads (§1) + conversion (§2): converting creates/links account + contact +
// deal server-side and stamps `converted_to`, so the row goes read-only after.

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import { Badge, Button, Card, ErrorNote, Field, Spinner } from "../../shared/legacy-ui";

interface Lead {
  id: string;
  name: string;
  email?: string | null;
  phone?: string | null;
  source?: string | null;
  status: string;
  converted_to?: {
    account_id: string | null;
    contact_id: string | null;
    deal_id: string | null;
  };
}

const STATUS_TONE: Record<string, string> = {
  new: "neutral", contacted: "neutral", qualified: "ok",
  unqualified: "danger", converted: "ok",
};

export function LeadsSection(props: { canWrite: boolean; openNew?: boolean }) {
  const [leads, setLeads] = useState<Lead[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(Boolean(props.openNew));
  const [converting, setConverting] = useState<Lead | null>(null);

  const load = useCallback(() => {
    api<Lead[]>("/crm/leads?page_size=100")
      .then((r) => setLeads(r.data)).catch(setError);
  }, []);

  useEffect(load, [load]);

  if (!leads) return <Spinner />;

  return (
    <>
      <Card
        title={`Leads (${leads.length})`}
        actions={props.canWrite && (
          <Button onClick={() => setCreating(true)}>New lead</Button>
        )}
      >
        <ErrorNote error={error} />
        <table className="table">
          <thead>
            <tr>
              <th>Name</th><th>Email</th><th>Source</th><th>Status</th>
              {props.canWrite && <th></th>}
            </tr>
          </thead>
          <tbody>
            {leads.map((l) => (
              <tr key={l.id}>
                <td><b>{l.name}</b></td>
                <td className="muted">{l.email ?? "—"}</td>
                <td className="muted">{l.source ?? "—"}</td>
                <td><Badge tone={STATUS_TONE[l.status] ?? "neutral"}>{l.status}</Badge></td>
                {props.canWrite && (
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    {l.status === "converted" ? (
                      <span className="muted">converted</span>
                    ) : (
                      <Button variant="ghost" onClick={() => setConverting(l)}>
                        Convert
                      </Button>
                    )}
                  </td>
                )}
              </tr>
            ))}
            {leads.length === 0 && (
              <tr><td colSpan={5} className="muted">No leads yet.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
      {creating && (
        <LeadModal onDone={(ok) => { setCreating(false); if (ok) load(); }} />
      )}
      {converting && (
        <ConvertModal lead={converting}
          onDone={(ok) => { setConverting(null); if (ok) load(); }} />
      )}
    </>
  );
}

function LeadModal(props: { onDone: (ok: boolean) => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [source, setSource] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/crm/leads", {
        method: "POST",
        body: {
          name,
          email: email || null,
          phone: phone || null,
          source: source || null,
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
        <h3 style={{ marginBottom: 16 }}>New lead</h3>
        <ErrorNote error={error} />
        <form onSubmit={submit}>
          <Field label="Name">
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </Field>
          <Field label="Email">
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Phone">
            <input value={phone} onChange={(e) => setPhone(e.target.value)} />
          </Field>
          <Field label="Source">
            <input value={source} onChange={(e) => setSource(e.target.value)}
              placeholder="referral, web, event…" />
          </Field>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
            <Button variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Create lead"}</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function ConvertModal(props: { lead: Lead; onDone: (ok: boolean) => void }) {
  const [accountName, setAccountName] = useState(props.lead.name);
  const [dealTitle, setDealTitle] = useState(`${props.lead.name} — new business`);
  const [amount, setAmount] = useState("0");
  const [close, setClose] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api(`/crm/leads/${props.lead.id}/convert`, {
        method: "POST",
        body: {
          account_name: accountName,
          deal_title: dealTitle,
          amount: Number(amount),
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
        <h3 style={{ marginBottom: 4 }}>Convert “{props.lead.name}”</h3>
        <p className="muted" style={{ marginBottom: 16, fontSize: 13 }}>
          Creates a linked account, contact and deal.
        </p>
        <ErrorNote error={error} />
        <form onSubmit={submit}>
          <Field label="Account name">
            <input value={accountName} onChange={(e) => setAccountName(e.target.value)}
              required />
          </Field>
          <Field label="Deal title">
            <input value={dealTitle} onChange={(e) => setDealTitle(e.target.value)}
              required />
          </Field>
          <Field label="Deal amount">
            <input type="number" min="0" value={amount}
              onChange={(e) => setAmount(e.target.value)} />
          </Field>
          <Field label="Expected close date">
            <input type="date" value={close} onChange={(e) => setClose(e.target.value)} />
          </Field>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
            <Button variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Converting…" : "Convert"}</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
