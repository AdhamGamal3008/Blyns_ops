// Job-cost capture (§3.9, acceptance #7): labor/material actuals post a balanced
// Dr COGS / Cr AP entry to Finance and roll into the project budget. A material
// actual also draws down the Stage-8 commitment, so a posted cost refreshes the
// parent budget header.

import { Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import {
  Badge,
  Button,
  CardHeader,
  Checkbox,
  DataState,
  DataTable,
  type DataTableColumn,
  Field,
  FormModal,
  Input,
  Select,
} from "../../shared/ui";
import { humanize, money, type JobCost } from "./types";

const COST_TYPES: JobCost["cost_type"][] = ["labor", "material", "subcontractor", "machine"];

export function JobCostsSection(props: {
  projectId: string; canWrite: boolean; currency: string; onChanged: () => void;
}) {
  const [items, setItems] = useState<JobCost[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    setError(null);
    api<JobCost[]>(`/projects/${props.projectId}/job-costs?page_size=100`)
      .then((r) => setItems(r.data)).catch(setError);
  }, [props.projectId]);

  useEffect(load, [load]);

  const total = (items ?? []).reduce((s, c) => s + c.amount, 0);

  const columns: DataTableColumn<JobCost>[] = [
    {
      key: "cost_type",
      header: "Type",
      sortable: true,
      accessor: (c) => <Badge tone="neutral">{c.cost_type}</Badge>,
      sortValue: (c) => c.cost_type,
    },
    { key: "description", header: "Description", accessor: (c) => c.description || "—" },
    {
      key: "stage_key",
      header: "Stage",
      sortable: true,
      accessor: (c) => humanize(c.stage_key),
    },
    {
      key: "amount",
      header: "Amount",
      numeric: true,
      sortable: true,
      accessor: (c) => money(c.amount, props.currency),
      sortValue: (c) => c.amount,
    },
    {
      key: "posted",
      header: "Posted",
      accessor: (c) => (c.posted_to_finance_ref ? <Badge tone="success">ledger</Badge> : "—"),
    },
  ];

  return (
    <section>
      <CardHeader
        title="Job costs"
        description={`${money(total, props.currency)} captured across ${items?.length ?? 0} entries`}
        actions={
          props.canWrite && (
            <Button size="compact" onClick={() => setCreating(true)}>
              <Plus size={15} aria-hidden="true" />
              Add cost
            </Button>
          )
        }
      />
      <DataState
        loading={!items && !error}
        error={items ? null : error}
        onRetry={load}
        isEmpty={items?.length === 0}
        emptyTitle="No costs captured yet"
        emptyDescription="Labor and material actuals post to Finance and roll into the budget."
      >
        <DataTable
          data={items ?? []}
          columns={columns}
          getRowId={(c) => c.id}
          searchPlaceholder="Search costs…"
        />
      </DataState>

      <CostModal
        open={creating}
        projectId={props.projectId}
        currency={props.currency}
        onDone={(ok) => { setCreating(false); if (ok) { load(); props.onChanged(); } }}
      />
    </section>
  );
}

function CostModal(props: {
  open: boolean; projectId: string; currency: string; onDone: (ok: boolean) => void;
}) {
  const [costType, setCostType] = useState<JobCost["cost_type"]>("labor");
  const [description, setDescription] = useState("");
  const [hours, setHours] = useState("");
  const [quantity, setQuantity] = useState("");
  const [unitCost, setUnitCost] = useState("");
  const [post, setPost] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const isLabor = costType === "labor";
  const measure = Number(isLabor ? hours : quantity) || 0;
  const amount = measure * (Number(unitCost) || 0);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api(`/projects/${props.projectId}/job-costs`, {
        method: "POST",
        body: {
          cost_type: costType,
          description: description || null,
          hours: isLabor ? Number(hours) : 0,
          quantity: isLabor ? 0 : Number(quantity),
          unit_cost: Number(unitCost),
          post_to_finance: post,
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
      title="Add job cost"
      description={`Amount ${money(amount, props.currency)}`}
      onSubmit={submit}
      error={error}
      errorTitle="Could not post the cost"
      busy={busy}
      submitDisabled={amount <= 0}
      submitLabel="Add cost"
      busyLabel="Posting…"
    >
      <Field label="Cost type">
        <Select
          value={costType}
          onValueChange={(v) => setCostType(v as JobCost["cost_type"])}
          options={COST_TYPES.map((t) => ({ value: t, label: humanize(t) }))}
        />
      </Field>
      <Field label="Description">
        <Input value={description} onChange={(e) => setDescription(e.target.value)} />
      </Field>
      <Field label={isLabor ? "Hours" : "Quantity"} required>
        <Input type="number" step="any" min="0" required
          value={isLabor ? hours : quantity}
          onChange={(e) => (isLabor ? setHours : setQuantity)(e.target.value)} />
      </Field>
      <Field label="Unit cost" required>
        <Input type="number" step="any" min="0" value={unitCost} required
          onChange={(e) => setUnitCost(e.target.value)} />
      </Field>
      <Checkbox
        label="Post to Finance (Dr COGS / Cr AP)"
        checked={post}
        onCheckedChange={(v) => setPost(v === true)}
      />
    </FormModal>
  );
}
