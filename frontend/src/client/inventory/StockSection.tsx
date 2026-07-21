// On-hand by product × warehouse (§3 /stock-levels). Stock is never edited
// here — every change is posted as a movement and the cache follows the ledger.

import { ArrowLeftRight, Plus } from "lucide-react";
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
  NativeSelect,
  Row,
} from "../../shared/ui";
import { DEFAULT_UNIT, type Product, type StockLevel, type Warehouse } from "./types";

export function StockSection(props: { canWrite: boolean; openMove?: boolean }) {
  const [levels, setLevels] = useState<StockLevel[] | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [moving, setMoving] = useState(Boolean(props.openMove));
  const [transferring, setTransferring] = useState(false);

  const load = useCallback(() => {
    api<StockLevel[]>("/inventory/stock-levels?page_size=100")
      .then((r) => setLevels(r.data)).catch(setError);
    api<Product[]>("/inventory/products?page_size=100")
      .then((r) => setProducts(r.data)).catch(() => {});
    api<Warehouse[]>("/inventory/warehouses?page_size=100")
      .then((r) => setWarehouses(r.data)).catch(() => {});
  }, []);

  useEffect(load, [load]);

  const product = (id: string) => products.find((p) => p.id === id);
  const warehouse = (id: string) => warehouses.find((w) => w.id === id);

  const rows = (levels ?? []).filter((l) => product(l.product_id));

  const columns: DataTableColumn<StockLevel>[] = [
    { key: "sku", header: "SKU", sortable: true, accessor: (l) => product(l.product_id)!.sku, sortValue: (l) => product(l.product_id)!.sku },
    {
      key: "product",
      header: "Product",
      sortable: true,
      accessor: (l) => <b>{product(l.product_id)!.name}</b>,
      sortValue: (l) => product(l.product_id)!.name,
    },
    {
      key: "warehouse",
      header: "Warehouse",
      sortable: true,
      accessor: (l) => warehouse(l.warehouse_id)?.name ?? "—",
      sortValue: (l) => warehouse(l.warehouse_id)?.name ?? "",
    },
    {
      key: "on_hand",
      header: "On hand",
      numeric: true,
      sortable: true,
      accessor: (l) => `${l.on_hand} ${product(l.product_id)!.unit ?? DEFAULT_UNIT}`,
      sortValue: (l) => l.on_hand,
    },
    {
      key: "status",
      header: "Status",
      accessor: (l) => {
        const point = product(l.product_id)!.reorder_point ?? 0;
        const low = point > 0 && l.on_hand <= point;
        return l.on_hand < 0
          ? <Badge tone="danger">negative</Badge>
          : low
            ? <Badge tone="warning">low</Badge>
            : <Badge tone="success">ok</Badge>;
      },
    },
  ];

  return (
    <section>
      <CardHeader
        title="Stock on hand"
        description="Derived from the movement ledger — never edited directly."
        actions={
          props.canWrite && (
            <Row gap={2}>
              <Button variant="secondary" size="compact" onClick={() => setTransferring(true)}>
                <ArrowLeftRight size={15} aria-hidden="true" />
                Transfer
              </Button>
              <Button size="compact" onClick={() => setMoving(true)}>
                <Plus size={15} aria-hidden="true" />
                New movement
              </Button>
            </Row>
          )
        }
      />

      {error != null && levels != null && (
        <Banner tone="danger" title="That action failed">{errorText(error)}</Banner>
      )}

      <DataState
        loading={!levels && !error}
        error={levels ? null : error}
        onRetry={load}
        isEmpty={levels != null && rows.length === 0}
        emptyTitle="No stock yet"
        emptyDescription="Post a receipt to get started."
      >
        <DataTable
          data={rows}
          columns={columns}
          getRowId={(l) => l.id}
          searchPlaceholder="Search stock…"
        />
      </DataState>

      {moving && (
        <MovementModal products={products} warehouses={warehouses}
          onDone={(ok) => { setMoving(false); if (ok) load(); }} />
      )}
      {transferring && (
        <TransferModal products={products} warehouses={warehouses}
          onDone={(ok) => { setTransferring(false); if (ok) load(); }} />
      )}
    </section>
  );
}

const TYPES = [
  { value: "receipt", label: "Receipt (add stock)" },
  { value: "issue", label: "Issue (remove stock)" },
  { value: "adjustment", label: "Adjustment (correct a discrepancy)" },
];

export function MovementModal(props: {
  products: Product[];
  warehouses: Warehouse[];
  onDone: (ok: boolean) => void;
}) {
  const [productId, setProductId] = useState(props.products[0]?.id ?? "");
  const [warehouseId, setWarehouseId] = useState(props.warehouses[0]?.id ?? "");
  const [type, setType] = useState("receipt");
  const [qty, setQty] = useState("1");
  const [note, setNote] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  // §2: an adjustment must explain itself, and is the one type that is signed.
  const isAdjustment = type === "adjustment";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/inventory/movements", {
        method: "POST",
        body: {
          product_id: productId, warehouse_id: warehouseId, type,
          qty: Number(qty), note: note || null,
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
      title="New movement"
      onSubmit={submit}
      error={error}
      errorTitle="Could not post the movement"
      busy={busy}
      submitLabel="Post movement"
      busyLabel="Posting…"
    >
      <Field label="Product">
        <NativeSelect
          value={productId}
          onChange={(e) => setProductId(e.target.value)}
          required
          options={props.products.map((p) => ({ value: p.id, label: `${p.sku} — ${p.name}` }))}
        />
      </Field>
      <Field label="Warehouse">
        <NativeSelect
          value={warehouseId}
          onChange={(e) => setWarehouseId(e.target.value)}
          required
          options={props.warehouses.map((w) => ({ value: w.id, label: w.name }))}
        />
      </Field>
      <Field label="Type">
        <NativeSelect
          value={type}
          onChange={(e) => setType(e.target.value)}
          options={TYPES}
        />
      </Field>
      <Field label={isAdjustment ? "Qty (+/- to correct)" : "Qty"}>
        <Input type="number" step="any" value={qty} required
          min={isAdjustment ? undefined : "0.0001"}
          onChange={(e) => setQty(e.target.value)} />
      </Field>
      <Field label="Note" required={isAdjustment}>
        <Input value={note} onChange={(e) => setNote(e.target.value)}
          required={isAdjustment}
          placeholder={isAdjustment ? "why the count changed" : "optional"} />
      </Field>
    </FormModal>
  );
}

function TransferModal(props: {
  products: Product[];
  warehouses: Warehouse[];
  onDone: (ok: boolean) => void;
}) {
  const [productId, setProductId] = useState(props.products[0]?.id ?? "");
  const [from, setFrom] = useState(props.warehouses[0]?.id ?? "");
  const [to, setTo] = useState(props.warehouses[1]?.id ?? "");
  const [qty, setQty] = useState("1");
  const [note, setNote] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const tooFewWarehouses = props.warehouses.length < 2;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/inventory/transfers", {
        method: "POST",
        body: {
          product_id: productId, from_warehouse_id: from, to_warehouse_id: to,
          qty: Number(qty), note: note || null,
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
      title="Transfer stock"
      description="Posts a balanced issue + receipt across the two warehouses."
      onSubmit={submit}
      error={error}
      errorTitle="Could not transfer the stock"
      busy={busy}
      submitDisabled={tooFewWarehouses}
      submitLabel="Transfer"
      busyLabel="Transferring…"
    >
      {tooFewWarehouses && (
        <Banner tone="warning" title="Add a second warehouse first">
          A transfer needs somewhere to move stock to.
        </Banner>
      )}
      <Field label="Product">
        <NativeSelect
          value={productId}
          onChange={(e) => setProductId(e.target.value)}
          required
          options={props.products.map((p) => ({ value: p.id, label: `${p.sku} — ${p.name}` }))}
        />
      </Field>
      <Field label="From">
        <NativeSelect
          value={from}
          onChange={(e) => setFrom(e.target.value)}
          required
          options={props.warehouses.map((w) => ({ value: w.id, label: w.name }))}
        />
      </Field>
      <Field label="To">
        <NativeSelect
          value={to}
          onChange={(e) => setTo(e.target.value)}
          required
          options={props.warehouses.map((w) => ({ value: w.id, label: w.name }))}
        />
      </Field>
      <Field label="Qty">
        <Input type="number" step="any" min="0.0001" value={qty} required
          onChange={(e) => setQty(e.target.value)} />
      </Field>
      <Field label="Note">
        <Input value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
    </FormModal>
  );
}
