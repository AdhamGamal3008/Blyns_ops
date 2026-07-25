// Accounts (§1). Deleting is guarded server-side while open deals exist.

import { Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import {
  Badge,
  type BadgeTone,
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
  NativeSelect,
  Select,
} from "../../shared/ui";
import { DataTransfer } from "../../shared/csv/DataTransfer";

interface Account {
  id: string;
  name: string;
  industry?: string | null;
  website?: string | null;
  phone?: string | null;
  status: string;
}

const STATUSES = ["prospect", "customer", "inactive"];
const TONE: Record<string, BadgeTone> = {
  prospect: "neutral", customer: "success", inactive: "warning",
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

  const columns: DataTableColumn<Account>[] = [
    { key: "name", header: "Name", sortable: true, accessor: (a) => <b>{a.name}</b>, sortValue: (a) => a.name },
    { key: "industry", header: "Industry", sortable: true, accessor: (a) => a.industry ?? "—" },
    { key: "phone", header: "Phone", accessor: (a) => a.phone ?? "—" },
    {
      key: "status",
      header: "Status",
      sortable: true,
      sortValue: (a) => a.status,
      accessor: (a) =>
        props.canWrite ? (
          // inline status change: a native picker keeps the row compact
          <NativeSelect
            selectSize="compact"
            aria-label={`Status for ${a.name}`}
            value={a.status}
            onChange={(e) => setStatus(a, e.target.value)}
            options={STATUSES.map((s) => ({ value: s, label: s }))}
          />
        ) : (
          <Badge tone={TONE[a.status] ?? "neutral"}>{a.status}</Badge>
        ),
    },
    ...(props.canWrite
      ? [{
          key: "actions",
          header: "",
          accessor: (a: Account) => (
            <Button variant="ghost" size="compact" onClick={() => remove(a)}>Delete</Button>
          ),
        }]
      : []),
  ];

  return (
    <section>
      <CardHeader
        title="Accounts"
        description={accounts ? `${accounts.length} on the books` : "Customer and prospect accounts"}
        actions={
          <>
            <DataTransfer module="crm" entity="accounts" canWrite={props.canWrite}
              onImported={load} />
            {props.canWrite && (
              <Button size="compact" onClick={() => setCreating(true)}>
                <Plus size={15} aria-hidden="true" />
                New account
              </Button>
            )}
          </>
        }
      />

      {error != null && accounts != null && (
        <Banner tone="danger" title="That action failed">{errorText(error)}</Banner>
      )}

      <DataState
        loading={!accounts && !error}
        error={accounts ? null : error}
        onRetry={load}
        isEmpty={accounts?.length === 0}
        emptyTitle="No accounts yet"
        emptyDescription="Convert a lead, or create one directly."
      >
        <DataTable
          data={accounts ?? []}
          columns={columns}
          getRowId={(a) => a.id}
          searchPlaceholder="Search accounts…"
        />
      </DataState>

      <AccountModal open={creating} onDone={(ok) => { setCreating(false); if (ok) load(); }} />
    </section>
  );
}

function AccountModal(props: { open: boolean; onDone: (ok: boolean) => void }) {
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
    <FormModal
      open={props.open}
      onOpenChange={(o) => !o && props.onDone(false)}
      title="New account"
      onSubmit={submit}
      error={error}
      errorTitle="Could not create the account"
      busy={busy}
      submitLabel="Create account"
    >
      <Field label="Name" required>
        <Input value={name} onChange={(e) => setName(e.target.value)} required />
      </Field>
      <Field label="Industry">
        <Input value={industry} onChange={(e) => setIndustry(e.target.value)} />
      </Field>
      <Field label="Phone">
        <Input value={phone} onChange={(e) => setPhone(e.target.value)} />
      </Field>
      <Field label="Status">
        <Select
          value={status}
          onValueChange={setStatus}
          options={STATUSES.map((s) => ({ value: s, label: s }))}
        />
      </Field>
    </FormModal>
  );
}
