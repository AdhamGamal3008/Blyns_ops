// Leads (§1) + conversion (§2): converting creates/links account + contact +
// deal server-side and stamps `converted_to`, so the row goes read-only after.

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
} from "../../shared/ui";

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

const STATUS_TONE: Record<string, BadgeTone> = {
  new: "neutral", contacted: "info", qualified: "success",
  unqualified: "danger", converted: "success",
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

  const columns: DataTableColumn<Lead>[] = [
    { key: "name", header: "Name", sortable: true, accessor: (l) => <b>{l.name}</b>, sortValue: (l) => l.name },
    { key: "email", header: "Email", sortable: true, accessor: (l) => l.email ?? "—" },
    { key: "source", header: "Source", sortable: true, accessor: (l) => l.source ?? "—" },
    {
      key: "status",
      header: "Status",
      sortable: true,
      accessor: (l) => <Badge tone={STATUS_TONE[l.status] ?? "neutral"}>{l.status}</Badge>,
      sortValue: (l) => l.status,
    },
    ...(props.canWrite
      ? [{
          key: "actions",
          header: "",
          accessor: (l: Lead) =>
            l.status === "converted" ? (
              <span>converted</span>
            ) : (
              <Button variant="ghost" size="compact" onClick={() => setConverting(l)}>
                Convert
              </Button>
            ),
        }]
      : []),
  ];

  return (
    <section>
      <CardHeader
        title="Leads"
        description={leads ? `${leads.length} in the funnel` : "Inbound and sourced leads"}
        actions={
          props.canWrite && (
            <Button size="compact" onClick={() => setCreating(true)}>
              <Plus size={15} aria-hidden="true" />
              New lead
            </Button>
          )
        }
      />

      {error != null && leads != null && (
        <Banner tone="danger" title="That action failed">{errorText(error)}</Banner>
      )}

      <DataState
        loading={!leads && !error}
        error={leads ? null : error}
        onRetry={load}
        isEmpty={leads?.length === 0}
        emptyTitle="No leads yet"
        emptyDescription="Capture one to start the funnel."
      >
        <DataTable
          data={leads ?? []}
          columns={columns}
          getRowId={(l) => l.id}
          searchPlaceholder="Search leads…"
        />
      </DataState>

      <LeadModal open={creating} onDone={(ok) => { setCreating(false); if (ok) load(); }} />
      {converting && (
        <ConvertModal lead={converting}
          onDone={(ok) => { setConverting(null); if (ok) load(); }} />
      )}
    </section>
  );
}

function LeadModal(props: { open: boolean; onDone: (ok: boolean) => void }) {
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
    <FormModal
      open={props.open}
      onOpenChange={(o) => !o && props.onDone(false)}
      title="New lead"
      onSubmit={submit}
      error={error}
      errorTitle="Could not create the lead"
      busy={busy}
      submitLabel="Create lead"
    >
      <Field label="Name" required>
        <Input value={name} onChange={(e) => setName(e.target.value)} required />
      </Field>
      <Field label="Email">
        <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      </Field>
      <Field label="Phone">
        <Input value={phone} onChange={(e) => setPhone(e.target.value)} />
      </Field>
      <Field label="Source">
        <Input value={source} onChange={(e) => setSource(e.target.value)}
          placeholder="referral, web, event…" />
      </Field>
    </FormModal>
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
    <FormModal
      open
      onOpenChange={(o) => !o && props.onDone(false)}
      title={`Convert “${props.lead.name}”`}
      description="Creates a linked account, contact and deal."
      onSubmit={submit}
      error={error}
      errorTitle="Could not convert the lead"
      busy={busy}
      submitLabel="Convert"
      busyLabel="Converting…"
    >
      <Field label="Account name" required>
        <Input value={accountName} onChange={(e) => setAccountName(e.target.value)} required />
      </Field>
      <Field label="Deal title" required>
        <Input value={dealTitle} onChange={(e) => setDealTitle(e.target.value)} required />
      </Field>
      <Field label="Deal amount">
        <Input type="number" min="0" value={amount} onChange={(e) => setAmount(e.target.value)} />
      </Field>
      <Field label="Expected close date">
        <Input type="date" value={close} onChange={(e) => setClose(e.target.value)} />
      </Field>
    </FormModal>
  );
}
