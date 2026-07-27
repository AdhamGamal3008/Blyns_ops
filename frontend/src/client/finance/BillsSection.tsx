// Vendor bills (AP) — the mirror of invoices (§1).

import { Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import type { CsvGrants } from "../../shared/csv/access";
import { DataTransfer } from "../../shared/csv/DataTransfer";
import {
  Badge,
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
import { STATUS_TONE, money, type Bill } from "./types";
import styles from "./Finance.module.css";

export function BillsSection(props: { canWrite: boolean; csv: CsvGrants }) {
  const [bills, setBills] = useState<Bill[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    setError(null);
    api<Bill[]>("/finance/bills?page_size=100")
      .then((r) => setBills(r.data)).catch(setError);
  }, []);

  useEffect(load, [load]);

  async function send(bill: Bill) {
    setError(null);
    try {
      await api(`/finance/bills/${bill.id}/send`, { method: "POST" });
      load();
    } catch (err) {
      setError(err);
    }
  }

  async function pay(bill: Bill) {
    setError(null);
    try {
      await api("/finance/payments", {
        method: "POST",
        body: {
          type: "vendor_payment", ref_doc_type: "bill", ref_doc_id: bill.id,
          amount: bill.total - (bill.paid_amount ?? 0), method: "bank",
        },
      });
      load();
    } catch (err) {
      setError(err);
    }
  }

  const columns: DataTableColumn<Bill>[] = [
    { key: "number", header: "Number", sortable: true, accessor: (b) => b.number ?? "—" },
    {
      key: "vendor",
      header: "Vendor",
      sortable: true,
      accessor: (b) => <b>{b.vendor_ref?.name}</b>,
      sortValue: (b) => b.vendor_ref?.name ?? "",
    },
    {
      key: "due_date",
      header: "Due",
      sortable: true,
      accessor: (b) => new Date(b.due_date).toLocaleDateString(),
      sortValue: (b) => b.due_date,
    },
    {
      key: "total",
      header: "Total",
      numeric: true,
      sortable: true,
      accessor: (b) => money(b.total, b.currency),
      sortValue: (b) => b.total,
    },
    {
      key: "outstanding",
      header: "Outstanding",
      numeric: true,
      sortable: true,
      sortValue: (b) => b.total - (b.paid_amount ?? 0),
      accessor: (b) => {
        const outstanding = b.total - (b.paid_amount ?? 0);
        return (
          <b className={outstanding > 0 ? styles.owing : styles.settled}>
            {money(outstanding, b.currency)}
          </b>
        );
      },
    },
    {
      key: "status",
      header: "Status",
      sortable: true,
      accessor: (b) => <Badge tone={STATUS_TONE[b.status] ?? "neutral"}>{b.status}</Badge>,
      sortValue: (b) => b.status,
    },
    ...(props.canWrite
      ? [{
          key: "actions",
          header: "",
          accessor: (b: Bill) => (
            <>
              {b.status === "draft" && (
                <Button variant="ghost" size="compact" onClick={() => send(b)}>Post</Button>
              )}
              {(b.status === "sent" || b.status === "partly_paid") && (
                <Button variant="ghost" size="compact" onClick={() => pay(b)}>Pay in full</Button>
              )}
            </>
          ),
        }]
      : []),
  ];

  return (
    <section>
      <CardHeader
        title="Bills"
        description="Vendor bills — the accounts-payable mirror of invoices."
        actions={
          <>
            <DataTransfer module="finance" entity="bills" csv={props.csv}
              exportOnly onImported={load} />
            {props.canWrite && (
              <Button size="compact" onClick={() => setCreating(true)}>
                <Plus size={15} aria-hidden="true" />
                New bill
              </Button>
            )}
          </>
        }
      />

      {error != null && bills != null && (
        <Banner tone="danger" title="That action failed">{errorText(error)}</Banner>
      )}

      <DataState
        loading={!bills && !error}
        error={bills ? null : error}
        onRetry={load}
        isEmpty={bills?.length === 0}
        emptyTitle="No bills yet"
      >
        <DataTable
          data={bills ?? []}
          columns={columns}
          getRowId={(b) => b.id}
          searchPlaceholder="Search bills…"
        />
      </DataState>

      <BillModal open={creating} onDone={(ok) => { setCreating(false); if (ok) load(); }} />
    </section>
  );
}

function BillModal(props: { open: boolean; onDone: (ok: boolean) => void }) {
  const [vendor, setVendor] = useState("");
  const [due, setDue] = useState("");
  const [description, setDescription] = useState("");
  const [qty, setQty] = useState("1");
  const [unitPrice, setUnitPrice] = useState("0");
  const [taxRate, setTaxRate] = useState("0");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/finance/bills", {
        method: "POST",
        body: {
          vendor_ref: { name: vendor },
          due_date: new Date(due).toISOString(),
          lines: [{
            description, qty: Number(qty),
            unit_price: Number(unitPrice), tax_rate: Number(taxRate),
          }],
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
      title="New bill"
      onSubmit={submit}
      error={error}
      errorTitle="Could not save the bill"
      busy={busy}
      submitLabel="Save draft"
    >
      <Field label="Vendor" required>
        <Input value={vendor} onChange={(e) => setVendor(e.target.value)} required />
      </Field>
      <Field label="Due date" required>
        <Input type="date" value={due} onChange={(e) => setDue(e.target.value)} required />
      </Field>
      <Field label="Description" required>
        <Input value={description} onChange={(e) => setDescription(e.target.value)} required />
      </Field>
      <Field label="Qty">
        <Input type="number" step="any" min="0.0001" value={qty}
          onChange={(e) => setQty(e.target.value)} required />
      </Field>
      <Field label="Unit price">
        <Input type="number" step="any" min="0" value={unitPrice}
          onChange={(e) => setUnitPrice(e.target.value)} required />
      </Field>
      <Field label="Tax rate (%)">
        <Input type="number" step="any" min="0" max="100" value={taxRate}
          onChange={(e) => setTaxRate(e.target.value)} />
      </Field>
    </FormModal>
  );
}
