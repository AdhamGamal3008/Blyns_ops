// Contacts (§1) — a contact optionally belongs to an account.

import { Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import {
  Banner,
  Button,
  CardHeader,
  DataState,
  DataTable,
  type DataTableColumn,
  errorText,
  Field,
  FormModal,
  Input,
  Select,
} from "../../shared/ui";
import type { CsvGrants } from "../../shared/csv/access";
import { DataTransfer } from "../../shared/csv/DataTransfer";

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

const NO_ACCOUNT = "__none";

export function ContactsSection(props: { canWrite: boolean; csv: CsvGrants; openNew?: boolean }) {
  const [contacts, setContacts] = useState<Contact[] | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(Boolean(props.openNew));

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

  const columns: DataTableColumn<Contact>[] = [
    {
      key: "name",
      header: "Name",
      sortable: true,
      sortValue: (c) => `${c.first_name} ${c.last_name}`,
      accessor: (c) => (
        <>
          <b>{c.first_name} {c.last_name}</b>
          {c.title && <div>{c.title}</div>}
        </>
      ),
    },
    {
      key: "account",
      header: "Account",
      sortable: true,
      accessor: (c) => accountName(c.account_id),
      sortValue: (c) => accountName(c.account_id),
    },
    { key: "email", header: "Email", sortable: true, accessor: (c) => c.email ?? "—" },
    { key: "phone", header: "Phone", accessor: (c) => c.phone ?? "—" },
    ...(props.canWrite
      ? [{
          key: "actions",
          header: "",
          accessor: (c: Contact) => (
            <Button variant="ghost" size="compact" onClick={() => remove(c)}>Delete</Button>
          ),
        }]
      : []),
  ];

  return (
    <section>
      <CardHeader
        title="Contacts"
        description={contacts ? `${contacts.length} people` : "People at your accounts"}
        actions={
          <>
            <DataTransfer module="crm" entity="contacts" csv={props.csv}
              onImported={load} />
            {props.canWrite && (
              <Button size="compact" onClick={() => setCreating(true)}>
                <Plus size={15} aria-hidden="true" />
                New contact
              </Button>
            )}
          </>
        }
      />

      {error != null && contacts != null && (
        <Banner tone="danger" title="That action failed">{errorText(error)}</Banner>
      )}

      <DataState
        loading={!contacts && !error}
        error={contacts ? null : error}
        onRetry={load}
        isEmpty={contacts?.length === 0}
        emptyTitle="No contacts yet"
      >
        <DataTable
          data={contacts ?? []}
          columns={columns}
          getRowId={(c) => c.id}
          searchPlaceholder="Search contacts…"
        />
      </DataState>

      <ContactModal
        open={creating}
        accounts={accounts}
        onDone={(ok) => { setCreating(false); if (ok) load(); }}
      />
    </section>
  );
}

function ContactModal(props: {
  open: boolean; accounts: Account[]; onDone: (ok: boolean) => void;
}) {
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [title, setTitle] = useState("");
  const [accountId, setAccountId] = useState(NO_ACCOUNT);
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
          account_id: accountId === NO_ACCOUNT ? null : accountId,
        },
      });
      props.onDone(true);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <FormModal
      open={props.open}
      onOpenChange={(o) => !o && props.onDone(false)}
      title="New contact"
      onSubmit={submit}
      error={error}
      errorTitle="Could not create the contact"
      busy={busy}
      submitLabel="Create contact"
    >
      <Field label="First name" required>
        <Input value={first} onChange={(e) => setFirst(e.target.value)} required />
      </Field>
      <Field label="Last name" required>
        <Input value={last} onChange={(e) => setLast(e.target.value)} required />
      </Field>
      <Field label="Account">
        <Select
          value={accountId}
          onValueChange={setAccountId}
          options={[
            { value: NO_ACCOUNT, label: "— none —" },
            ...props.accounts.map((a) => ({ value: a.id, label: a.name })),
          ]}
        />
      </Field>
      <Field label="Title">
        <Input value={title} onChange={(e) => setTitle(e.target.value)} />
      </Field>
      <Field label="Email">
        <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      </Field>
      <Field label="Phone">
        <Input value={phone} onChange={(e) => setPhone(e.target.value)} />
      </Field>
    </FormModal>
  );
}
