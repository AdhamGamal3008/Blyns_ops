// Invoices (§1/§2). A draft is editable and carries no number; sending claims
// the number and posts the journal entry; a posted invoice is only ever voided.

import { Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
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
  Row,
  Select,
} from "../../shared/ui";
import { STATUS_TONE, money, type Invoice } from "./types";
import styles from "./Finance.module.css";

export function InvoicesSection(props: { canWrite: boolean; openNew?: boolean }) {
  const [invoices, setInvoices] = useState<Invoice[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(Boolean(props.openNew));
  const [paying, setPaying] = useState<Invoice | null>(null);
  const [voiding, setVoiding] = useState<Invoice | null>(null);

  const load = useCallback(() => {
    setError(null);
    api<Invoice[]>("/finance/invoices?page_size=100")
      .then((r) => setInvoices(r.data)).catch(setError);
  }, []);

  useEffect(load, [load]);

  async function send(inv: Invoice) {
    setError(null);
    try {
      await api(`/finance/invoices/${inv.id}/send`, { method: "POST" });
      load();
    } catch (err) {
      setError(err);
    }
  }

  const columns: DataTableColumn<Invoice>[] = [
    { key: "number", header: "Number", sortable: true, accessor: (i) => i.number ?? "—" },
    {
      key: "customer",
      header: "Customer",
      sortable: true,
      accessor: (i) => <b>{i.customer_ref?.name}</b>,
      sortValue: (i) => i.customer_ref?.name ?? "",
    },
    {
      key: "due_date",
      header: "Due",
      sortable: true,
      accessor: (i) => new Date(i.due_date).toLocaleDateString(),
      sortValue: (i) => i.due_date,
    },
    {
      key: "total",
      header: "Total",
      numeric: true,
      sortable: true,
      accessor: (i) => money(i.total, i.currency),
      sortValue: (i) => i.total,
    },
    {
      key: "outstanding",
      header: "Outstanding",
      numeric: true,
      sortable: true,
      sortValue: (i) => i.total - (i.paid_amount ?? 0),
      accessor: (i) => {
        const outstanding = i.total - (i.paid_amount ?? 0);
        if (i.status === "void") return "—";
        return (
          <b className={outstanding > 0 ? styles.owing : styles.settled}>
            {money(outstanding, i.currency)}
          </b>
        );
      },
    },
    {
      key: "status",
      header: "Status",
      sortable: true,
      accessor: (i) => <Badge tone={STATUS_TONE[i.status] ?? "neutral"}>{i.status}</Badge>,
      sortValue: (i) => i.status,
    },
    ...(props.canWrite
      ? [{
          key: "actions",
          header: "",
          accessor: (inv: Invoice) => (
            <Row gap={2}>
              {inv.status === "draft" && (
                <Button variant="ghost" size="compact" onClick={() => send(inv)}>Send</Button>
              )}
              {(inv.status === "sent" || inv.status === "partly_paid") && (
                <>
                  <Button variant="ghost" size="compact" onClick={() => setPaying(inv)}>
                    Record payment
                  </Button>
                  <Button variant="ghost" size="compact" onClick={() => setVoiding(inv)}>
                    Void
                  </Button>
                </>
              )}
            </Row>
          ),
        }]
      : []),
  ];

  return (
    <section>
      <CardHeader
        title="Invoices"
        description="A draft has no number until it is sent; a sent invoice can only be voided."
        actions={
          props.canWrite && (
            <Button size="compact" onClick={() => setCreating(true)}>
              <Plus size={15} aria-hidden="true" />
              New invoice
            </Button>
          )
        }
      />

      {error != null && invoices != null && (
        <Banner tone="danger" title="That action failed">{errorText(error)}</Banner>
      )}

      <DataState
        loading={!invoices && !error}
        error={invoices ? null : error}
        onRetry={load}
        isEmpty={invoices?.length === 0}
        emptyTitle="No invoices yet"
      >
        <DataTable
          data={invoices ?? []}
          columns={columns}
          getRowId={(i) => i.id}
          searchPlaceholder="Search invoices…"
        />
      </DataState>

      <InvoiceModal open={creating} onDone={(ok) => { setCreating(false); if (ok) load(); }} />
      {paying && (
        <PaymentModal invoice={paying}
          onDone={(ok) => { setPaying(null); if (ok) load(); }} />
      )}
      {voiding && (
        <VoidModal invoice={voiding}
          onDone={(ok) => { setVoiding(null); if (ok) load(); }} />
      )}
    </section>
  );
}

function InvoiceModal(props: { open: boolean; onDone: (ok: boolean) => void }) {
  const [customer, setCustomer] = useState("");
  const [due, setDue] = useState("");
  const [description, setDescription] = useState("");
  const [qty, setQty] = useState("1");
  const [unitPrice, setUnitPrice] = useState("0");
  const [taxRate, setTaxRate] = useState("0");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const subtotal = Number(qty) * Number(unitPrice);
  const tax = subtotal * Number(taxRate) / 100;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/finance/invoices", {
        method: "POST",
        body: {
          customer_ref: { name: customer },
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
      title="New invoice"
      description="Saved as a draft — it gets its number when you send it."
      onSubmit={submit}
      error={error}
      errorTitle="Could not save the invoice"
      busy={busy}
      submitLabel="Save draft"
    >
      <Field label="Customer" required>
        <Input value={customer} onChange={(e) => setCustomer(e.target.value)} required />
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

      <p className={styles.totals}>
        Subtotal {money(subtotal)} · Tax {money(tax)} ·{" "}
        <b>Total {money(subtotal + tax)}</b>
      </p>
    </FormModal>
  );
}

export function PaymentModal(props: {
  invoice: Invoice;
  onDone: (ok: boolean) => void;
}) {
  const outstanding = props.invoice.total - (props.invoice.paid_amount ?? 0);
  const [amount, setAmount] = useState(String(outstanding));
  const [method, setMethod] = useState("bank");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/finance/payments", {
        method: "POST",
        body: {
          type: "customer_payment", ref_doc_type: "invoice",
          ref_doc_id: props.invoice.id, amount: Number(amount), method,
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
      title={`Record payment — ${props.invoice.number}`}
      description={`${money(outstanding, props.invoice.currency)} outstanding.`}
      onSubmit={submit}
      error={error}
      errorTitle="Could not record the payment"
      busy={busy}
      submitLabel="Record payment"
      busyLabel="Posting…"
    >
      <Field label="Amount" required>
        <Input type="number" step="0.01" min="0.01" max={outstanding}
          value={amount} onChange={(e) => setAmount(e.target.value)} required />
      </Field>
      <Field label="Method">
        <Select
          value={method}
          onValueChange={setMethod}
          options={[
            { value: "bank", label: "Bank" },
            { value: "cash", label: "Cash" },
            { value: "other", label: "Other" },
          ]}
        />
      </Field>
    </FormModal>
  );
}

function VoidModal(props: { invoice: Invoice; onDone: (ok: boolean) => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api(`/finance/invoices/${props.invoice.id}/void`, {
        method: "POST", body: { reason },
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
      title={`Void ${props.invoice.number}`}
      description="The original entry stays in the ledger; voiding posts a reversing entry."
      onSubmit={submit}
      error={error}
      errorTitle="Could not void the invoice"
      busy={busy}
      destructive
      submitLabel="Void invoice"
      busyLabel="Voiding…"
    >
      <Field label="Reason" required>
        <Input value={reason} onChange={(e) => setReason(e.target.value)}
          required placeholder="e.g. duplicate, issued in error" />
      </Field>
    </FormModal>
  );
}
