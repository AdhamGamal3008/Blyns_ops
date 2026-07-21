// Contacts (§1) — a contact optionally belongs to an account.

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import { Button, Card, ErrorNote, Field, Spinner } from "../../shared/legacy-ui";

interface Contact {
  id: string;
  account_id?: string | null;
  first_name: string;
  last_name: string;
  email?: string | null;
  phone?: string | null;
  title?: string | null;
}

interface Account {
  id: string;
  name: string;
}

export function ContactsSection(props: { canWrite: boolean }) {
  const [contacts, setContacts] = useState<Contact[] | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    api<Contact[]>("/crm/contacts?page_size=100")
      .then((r) => setContacts(r.data)).catch(setError);
    api<Account[]>("/crm/accounts?page_size=100")
      .then((r) => setAccounts(r.data)).catch(() => {});
  }, []);

  useEffect(load, [load]);

  const accountName = (id?: string | null) =>
    accounts.find((a) => a.id === id)?.name ?? "—";

  async function remove(c: Contact) {
    if (!window.confirm(`Delete contact “${c.first_name} ${c.last_name}”?`)) return;
    setError(null);
    try {
      await api(`/crm/contacts/${c.id}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError(err);
    }
  }

  if (!contacts) return <Spinner />;

  return (
    <>
      <Card
        title={`Contacts (${contacts.length})`}
        actions={props.canWrite && (
          <Button onClick={() => setCreating(true)}>New contact</Button>
        )}
      >
        <ErrorNote error={error} />
        <table className="table">
          <thead>
            <tr>
              <th>Name</th><th>Account</th><th>Email</th><th>Phone</th>
              {props.canWrite && <th></th>}
            </tr>
          </thead>
          <tbody>
            {contacts.map((c) => (
              <tr key={c.id}>
                <td>
                  <b>{c.first_name} {c.last_name}</b>
                  {c.title && <div className="muted">{c.title}</div>}
                </td>
                <td className="muted">{accountName(c.account_id)}</td>
                <td className="muted">{c.email ?? "—"}</td>
                <td className="muted">{c.phone ?? "—"}</td>
                {props.canWrite && (
                  <td style={{ textAlign: "right" }}>
                    <Button variant="ghost" onClick={() => remove(c)}>Delete</Button>
                  </td>
                )}
              </tr>
            ))}
            {contacts.length === 0 && (
              <tr><td colSpan={5} className="muted">No contacts yet.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
      {creating && (
        <ContactModal accounts={accounts}
          onDone={(ok) => { setCreating(false); if (ok) load(); }} />
      )}
    </>
  );
}

function ContactModal(props: { accounts: Account[]; onDone: (ok: boolean) => void }) {
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [title, setTitle] = useState("");
  const [accountId, setAccountId] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/crm/contacts", {
        method: "POST",
        body: {
          first_name: first, last_name: last,
          email: email || null, phone: phone || null, title: title || null,
          account_id: accountId || null,
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
        <h3 style={{ marginBottom: 16 }}>New contact</h3>
        <ErrorNote error={error} />
        <form onSubmit={submit}>
          <Field label="First name">
            <input value={first} onChange={(e) => setFirst(e.target.value)} required />
          </Field>
          <Field label="Last name">
            <input value={last} onChange={(e) => setLast(e.target.value)} required />
          </Field>
          <Field label="Account">
            <select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
              <option value="">— none —</option>
              {props.accounts.map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
          </Field>
          <Field label="Title">
            <input value={title} onChange={(e) => setTitle(e.target.value)} />
          </Field>
          <Field label="Email">
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Phone">
            <input value={phone} onChange={(e) => setPhone(e.target.value)} />
          </Field>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
            <Button variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Create contact"}</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
