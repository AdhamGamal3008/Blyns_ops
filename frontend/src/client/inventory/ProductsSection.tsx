// Products (§1). Deleting is refused server-side while stock is on hand.

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
  FormGrid,
  FormModal,
  Input,
  Row,
  Select,
} from "../../shared/ui";
import { DataTransfer } from "../../shared/csv/DataTransfer";
import { DEFAULT_UNIT, type Product } from "./types";

const UNITS = ["pcs", "kg", "box"];

export function ProductsSection(props: { canWrite: boolean }) {
  const [products, setProducts] = useState<Product[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    api<Product[]>("/inventory/products?page_size=100")
      .then((r) => setProducts(r.data)).catch(setError);
  }, []);

  useEffect(load, [load]);

  async function toggleActive(p: Product) {
    setError(null);
    try {
      await api(`/inventory/products/${p.id}`, {
        method: "PATCH", body: { is_active: !p.is_active },
      });
      load();
    } catch (err) {
      setError(err);
    }
  }

  async function remove(p: Product) {
    if (!window.confirm(`Delete product “${p.name}”?`)) return;
    setError(null);
    try {
      await api(`/inventory/products/${p.id}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError(err);
    }
  }

  const columns: DataTableColumn<Product>[] = [
    { key: "sku", header: "SKU", sortable: true },
    {
      key: "name",
      header: "Name",
      sortable: true,
      accessor: (p) => (
        <>
          <b>{p.name}</b>
          {p.category && <div>{p.category}</div>}
        </>
      ),
      sortValue: (p) => p.name,
    },
    { key: "unit", header: "Unit", accessor: (p) => p.unit ?? DEFAULT_UNIT },
    {
      key: "reorder_point",
      header: "Reorder point",
      numeric: true,
      sortable: true,
      accessor: (p) => ((p.reorder_point ?? 0) > 0 ? p.reorder_point : "—"),
      sortValue: (p) => p.reorder_point ?? 0,
    },
    {
      key: "status",
      header: "Status",
      sortable: true,
      accessor: (p) => (
        <Badge tone={p.is_active ? "success" : "neutral"}>
          {p.is_active ? "active" : "inactive"}
        </Badge>
      ),
      sortValue: (p) => String(p.is_active),
    },
    ...(props.canWrite
      ? [{
          key: "actions",
          header: "",
          accessor: (p: Product) => (
            <Row gap={2}>
              <Button variant="ghost" size="compact" onClick={() => toggleActive(p)}>
                {p.is_active ? "Deactivate" : "Activate"}
              </Button>
              <Button variant="ghost" size="compact" onClick={() => remove(p)}>Delete</Button>
            </Row>
          ),
        }]
      : []),
  ];

  return (
    <section>
      <CardHeader
        title="Products"
        description={products ? `${products.length} in the catalogue` : "Product catalogue"}
        actions={
          <>
            <DataTransfer module="inventory" entity="products"
              canWrite={props.canWrite} onImported={load} />
            {props.canWrite && (
              <Button size="compact" onClick={() => setCreating(true)}>
                <Plus size={15} aria-hidden="true" />
                New product
              </Button>
            )}
          </>
        }
      />

      {error != null && products != null && (
        <Banner tone="danger" title="That action failed">{errorText(error)}</Banner>
      )}

      <DataState
        loading={!products && !error}
        error={products ? null : error}
        onRetry={load}
        isEmpty={products?.length === 0}
        emptyTitle="No products yet"
      >
        <DataTable
          data={products ?? []}
          columns={columns}
          getRowId={(p) => p.id}
          searchPlaceholder="Search products…"
        />
      </DataState>

      <ProductModal open={creating} onDone={(ok) => { setCreating(false); if (ok) load(); }} />
    </section>
  );
}

function ProductModal(props: { open: boolean; onDone: (ok: boolean) => void }) {
  const [sku, setSku] = useState("");
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [unit, setUnit] = useState("pcs");
  const [costPrice, setCostPrice] = useState("0");
  const [salePrice, setSalePrice] = useState("0");
  const [reorderPoint, setReorderPoint] = useState("0");
  const [reorderQty, setReorderQty] = useState("0");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/inventory/products", {
        method: "POST",
        body: {
          sku, name, category: category || null, unit,
          cost_price: Number(costPrice), sale_price: Number(salePrice),
          reorder_point: Number(reorderPoint), reorder_qty: Number(reorderQty),
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
      title="New product"
      size="lg"
      onSubmit={submit}
      error={error}
      errorTitle="Could not create the product"
      busy={busy}
      submitLabel="Create product"
    >
      <FormGrid>
        <Field label="SKU" required>
          <Input value={sku} onChange={(e) => setSku(e.target.value)} required
            placeholder="SKU-001" />
        </Field>
        <Field label="Name" required>
          <Input value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <Field label="Category">
          <Input value={category} onChange={(e) => setCategory(e.target.value)} />
        </Field>
        <Field label="Unit">
          <Select
            value={unit}
            onValueChange={setUnit}
            options={UNITS.map((u) => ({ value: u, label: u }))}
          />
        </Field>
        <Field label="Cost price">
          <Input type="number" step="any" min="0" value={costPrice}
            onChange={(e) => setCostPrice(e.target.value)} />
        </Field>
        <Field label="Sale price">
          <Input type="number" step="any" min="0" value={salePrice}
            onChange={(e) => setSalePrice(e.target.value)} />
        </Field>
        <Field label="Reorder point" hint="0 means no reorder policy.">
          <Input type="number" step="any" min="0" value={reorderPoint}
            onChange={(e) => setReorderPoint(e.target.value)} />
        </Field>
        <Field label="Reorder qty">
          <Input type="number" step="any" min="0" value={reorderQty}
            onChange={(e) => setReorderQty(e.target.value)} />
        </Field>
      </FormGrid>
    </FormModal>
  );
}
