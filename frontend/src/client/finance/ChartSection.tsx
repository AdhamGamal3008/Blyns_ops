// Chart of accounts (§1). This is the Finance ledger — CRM's customers are a
// different thing entirely and live under CRM → Accounts.

import { Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import type { CsvGrants } from "../../shared/csv/access";
import { DataTransfer } from "../../shared/csv/DataTransfer";
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
  Select,
} from "../../shared/ui";
import type { Account } from "./types";

const TYPES = ["asset", "liability", "equity", "income", "expense"];
const TONE: Record<string, BadgeTone> = {
  asset: "success", liability: "warning", equity: "neutral",
  income: "info", expense: "danger",
};

export function ChartSection(props: { canWrite: boolean; csv: CsvGrants }) {
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

  const columns: DataTableColumn<Account>[] = [
    { key: "code", header: "Code", sortable: true },
    { key: "name", header: "Name", sortable: true, accessor: (a) => <b>{a.name}</b> },
    {
      key: "type",
      header: "Type",
      sortable: true,
      accessor: (a) => <Badge tone={TONE[a.type] ?? "neutral"}>{a.type}</Badge>,
      sortValue: (a) => a.type,
    },
    {
      key: "status",
      header: "Status",
      sortable: true,
      accessor: (a) => (a.is_active ? "active" : "inactive"),
      sortValue: (a) => String(a.is_active),
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
        title="Chart of accounts"
        description="The Finance ledger. CRM's customer accounts are a different thing entirely."
        actions={
          <>
            <DataTransfer module="finance" entity="accounts" csv={props.csv}
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
      >
        <DataTable
          data={accounts ?? []}
          columns={columns}
          getRowId={(a) => a.id}
          pageSize={15}
          searchPlaceholder="Search accounts…"
        />
      </DataState>

      <AccountModal open={creating} onDone={(ok) => { setCreating(false); if (ok) load(); }} />
    </section>
  );
}

function AccountModal(props: { open: boolean; onDone: (ok: boolean) => void }) {
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
      <Field label="Code" required>
        <Input value={code} onChange={(e) => setCode(e.target.value)} required
          placeholder="1200" />
      </Field>
      <Field label="Name" required>
        <Input value={name} onChange={(e) => setName(e.target.value)} required />
      </Field>
      <Field label="Type">
        <Select
          value={type}
          onValueChange={setType}
          options={TYPES.map((t) => ({ value: t, label: t }))}
        />
      </Field>
    </FormModal>
  );
}
