// Products (§1). Deleting is refused server-side while stock is on hand.

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import { Badge, Button, Card, ErrorNote, Field, Spinner } from "../../shared/ui";
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

  if (!products) return <Spinner />;

  return (
    <>
      <Card
        title={`Products (${products.length})`}
        actions={props.canWrite && (
          <Button onClick={() => setCreating(true)}>New product</Button>
        )}
      >
        <ErrorNote error={error} />
        <table className="table">
          <thead>
            <tr>
              <th>SKU</th><th>Name</th><th>Unit</th>
              <th style={{ textAlign: "right" }}>Reorder point</th>
              <th>Status</th>
              {props.canWrite && <th></th>}
            </tr>
          </thead>
          <tbody>
            {products.map((p) => (
              <tr key={p.id}>
                <td className="muted">{p.sku}</td>
                <td>
                  <b>{p.name}</b>
                  {p.category && <div className="muted">{p.category}</div>}
                </td>
                <td className="muted">{p.unit ?? DEFAULT_UNIT}</td>
                <td style={{ textAlign: "right" }} className="muted">
                  {(p.reorder_point ?? 0) > 0 ? p.reorder_point : "—"}
                </td>
                <td>
                  <Badge tone={p.is_active ? "ok" : "neutral"}>
                    {p.is_active ? "active" : "inactive"}
                  </Badge>
                </td>
                {props.canWrite && (
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <Button variant="ghost" onClick={() => toggleActive(p)}>
                      {p.is_active ? "Deactivate" : "Activate"}
                    </Button>{" "}
                    <Button variant="ghost" onClick={() => remove(p)}>Delete</Button>
                  </td>
                )}
              </tr>
            ))}
            {products.length === 0 && (
              <tr><td colSpan={6} className="muted">No products yet.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
      {creating && (
        <ProductModal onDone={(ok) => { setCreating(false); if (ok) load(); }} />
      )}
    </>
  );
}

function ProductModal(props: { onDone: (ok: boolean) => void }) {
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
    <div className="modal-backdrop" onClick={() => props.onDone(false)}>
      <div className="modal card" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 16 }}>New product</h3>
        <ErrorNote error={error} />
        <form onSubmit={submit}>
          <Field label="SKU">
            <input value={sku} onChange={(e) => setSku(e.target.value)} required
              placeholder="SKU-001" />
          </Field>
          <Field label="Name">
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </Field>
          <Field label="Category">
            <input value={category} onChange={(e) => setCategory(e.target.value)} />
          </Field>
          <Field label="Unit">
            <select value={unit} onChange={(e) => setUnit(e.target.value)}>
              {UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
            </select>
          </Field>
          <Field label="Cost price">
            <input type="number" step="any" min="0" value={costPrice}
              onChange={(e) => setCostPrice(e.target.value)} />
          </Field>
          <Field label="Sale price">
            <input type="number" step="any" min="0" value={salePrice}
              onChange={(e) => setSalePrice(e.target.value)} />
          </Field>
          <Field label="Reorder point (0 = no reorder policy)">
            <input type="number" step="any" min="0" value={reorderPoint}
              onChange={(e) => setReorderPoint(e.target.value)} />
          </Field>
          <Field label="Reorder qty">
            <input type="number" step="any" min="0" value={reorderQty}
              onChange={(e) => setReorderQty(e.target.value)} />
          </Field>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
            <Button variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Create product"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
