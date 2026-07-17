// Chart of accounts (§1). This is the Finance ledger — CRM's customers are a
// different thing entirely and live under CRM → Accounts.

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import { Badge, Button, Card, ErrorNote, Field, Spinner } from "../../shared/ui";
import type { Account } from "./types";

const TYPES = ["asset", "liability", "equity", "income", "expense"];
const TONE: Record<string, string> = {
  asset: "ok", liability: "warn", equity: "neutral",
  income: "ok", expense: "danger",
};

export function ChartSection(props: { canWrite: boolean }) {
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    setError(null);
    api<Account[]>("/finance/accounts?page_size=100")
      .then((r) => setAccounts(r.data)).catch(setError);
  }, []);

  useEffect(load, [load]);

  async function remove(a: Account) {
    if (!window.confirm(`Delete account “${a.code} ${a.name}”?`)) return;
    setError(null);
    try {
      await api(`/finance/accounts/${a.id}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError(err);
    }
  }

  if (!accounts) return <Spinner />;

  return (
    <>
      <Card
        title={`Chart of accounts (${accounts.length})`}
        actions={props.canWrite && (
          <Button onClick={() => setCreating(true)}>New account</Button>
        )}
      >
        <ErrorNote error={error} />
        <table className="table">
          <thead>
            <tr>
              <th>Code</th><th>Name</th><th>Type</th><th>Status</th>
              {props.canWrite && <th></th>}
            </tr>
          </thead>
          <tbody>
            {accounts.map((a) => (
              <tr key={a.id}>
                <td className="muted">{a.code}</td>
                <td><b>{a.name}</b></td>
                <td><Badge tone={TONE[a.type] ?? "neutral"}>{a.type}</Badge></td>
                <td className="muted">{a.is_active ? "active" : "inactive"}</td>
                {props.canWrite && (
                  <td style={{ textAlign: "right" }}>
                    <Button variant="ghost" onClick={() => remove(a)}>Delete</Button>
                  </td>
                )}
              </tr>
            ))}
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
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [type, setType] = useState("asset");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/finance/accounts", {
        method: "POST", body: { code, name, type },
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
          <Field label="Code">
            <input value={code} onChange={(e) => setCode(e.target.value)} required
              placeholder="1200" />
          </Field>
          <Field label="Name">
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </Field>
          <Field label="Type">
            <select value={type} onChange={(e) => setType(e.target.value)}>
              {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </Field>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
            <Button variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Create account"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
