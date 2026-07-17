// Accounts (§1). Deleting is guarded server-side while open deals exist.

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import { Badge, Button, Card, ErrorNote, Field, Spinner } from "../../shared/ui";

interface Account {
  id: string;
  name: string;
  industry?: string | null;
  website?: string | null;
  phone?: string | null;
  status: string;
}

const STATUSES = ["prospect", "customer", "inactive"];
const TONE: Record<string, string> = {
  prospect: "neutral", customer: "ok", inactive: "warn",
};

export function AccountsSection(props: { canWrite: boolean }) {
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    api<Account[]>("/crm/accounts?page_size=100")
      .then((r) => setAccounts(r.data)).catch(setError);
  }, []);

  useEffect(load, [load]);

  async function setStatus(a: Account, status: string) {
    setError(null);
    try {
      await api(`/crm/accounts/${a.id}`, { method: "PATCH", body: { status } });
      load();
    } catch (err) {
      setError(err);
    }
  }

  async function remove(a: Account) {
    if (!window.confirm(`Delete account “${a.name}”?`)) return;
    setError(null);
    try {
      await api(`/crm/accounts/${a.id}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError(err);
    }
  }

  if (!accounts) return <Spinner />;

  return (
    <>
      <Card
        title={`Accounts (${accounts.length})`}
        actions={props.canWrite && (
          <Button onClick={() => setCreating(true)}>New account</Button>
        )}
      >
        <ErrorNote error={error} />
        <table className="table">
          <thead>
            <tr>
              <th>Name</th><th>Industry</th><th>Phone</th><th>Status</th>
              {props.canWrite && <th></th>}
            </tr>
          </thead>
          <tbody>
            {accounts.map((a) => (
              <tr key={a.id}>
                <td><b>{a.name}</b></td>
                <td className="muted">{a.industry ?? "—"}</td>
                <td className="muted">{a.phone ?? "—"}</td>
                <td>
                  {props.canWrite ? (
                    <select value={a.status} style={{ width: 130 }}
                      onChange={(e) => setStatus(a, e.target.value)}>
                      {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  ) : (
                    <Badge tone={TONE[a.status] ?? "neutral"}>{a.status}</Badge>
                  )}
                </td>
                {props.canWrite && (
                  <td style={{ textAlign: "right" }}>
                    <Button variant="ghost" onClick={() => remove(a)}>Delete</Button>
                  </td>
                )}
              </tr>
            ))}
            {accounts.length === 0 && (
              <tr><td colSpan={5} className="muted">No accounts yet.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
      {creating && (
        <AccountModal onDone={(ok) => { setCreating(false); if (ok) load(); }} />
      )}
    </>
  );
}

function AccountModal(props: { onDone: (ok: boolean) => void }) {
  const [name, setName] = useState("");
  const [industry, setIndustry] = useState("");
  const [phone, setPhone] = useState("");
  const [status, setStatus] = useState("prospect");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/crm/accounts", {
        method: "POST",
        body: { name, industry: industry || null, phone: phone || null, status },
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
        <h3 style={{ marginBottom: 16 }}>New account</h3>
        <ErrorNote error={error} />
        <form onSubmit={submit}>
          <Field label="Name">
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </Field>
          <Field label="Industry">
            <input value={industry} onChange={(e) => setIndustry(e.target.value)} />
          </Field>
          <Field label="Phone">
            <input value={phone} onChange={(e) => setPhone(e.target.value)} />
          </Field>
          <Field label="Status">
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </Field>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
            <Button variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Create account"}</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
