// On-hand by product × warehouse (§3 /stock-levels). Stock is never edited
// here — every change is posted as a movement and the cache follows the ledger.

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import { Badge, Button, Card, ErrorNote, Field, Spinner } from "../../shared/legacy-ui";
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

  if (!levels) return <Spinner />;

  const rows = levels.filter((l) => product(l.product_id));

  return (
    <>
      <Card
        title="Stock on hand"
        actions={props.canWrite && (
          <>
            <Button variant="ghost" onClick={() => setTransferring(true)}>
              Transfer
            </Button>{" "}
            <Button onClick={() => setMoving(true)}>New movement</Button>
          </>
        )}
      >
        <ErrorNote error={error} />
        <table className="table">
          <thead>
            <tr>
              <th>SKU</th><th>Product</th><th>Warehouse</th>
              <th style={{ textAlign: "right" }}>On hand</th><th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((l) => {
              const p = product(l.product_id)!;
              const point = p.reorder_point ?? 0;
              const low = point > 0 && l.on_hand <= point;
              return (
                <tr key={l.id}>
                  <td className="muted">{p.sku}</td>
                  <td><b>{p.name}</b></td>
                  <td className="muted">{warehouse(l.warehouse_id)?.name ?? "—"}</td>
                  <td style={{ textAlign: "right" }}>
                    <b>{l.on_hand}</b>{" "}
                    <span className="muted">{p.unit ?? DEFAULT_UNIT}</span>
                  </td>
                  <td>
                    {l.on_hand < 0
                      ? <Badge tone="danger">negative</Badge>
                      : low
                        ? <Badge tone="warn">low</Badge>
                        : <Badge tone="ok">ok</Badge>}
                  </td>
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr><td colSpan={5} className="muted">
                No stock yet — post a receipt to get started.
              </td></tr>
            )}
          </tbody>
        </table>
      </Card>
      {moving && (
        <MovementModal products={products} warehouses={warehouses}
          onDone={(ok) => { setMoving(false); if (ok) load(); }} />
      )}
      {transferring && (
        <TransferModal products={products} warehouses={warehouses}
          onDone={(ok) => { setTransferring(false); if (ok) load(); }} />
      )}
    </>
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
    <div className="modal-backdrop" onClick={() => props.onDone(false)}>
      <div className="modal card" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 16 }}>New movement</h3>
        <ErrorNote error={error} />
        <form onSubmit={submit}>
          <Field label="Product">
            <select value={productId} onChange={(e) => setProductId(e.target.value)}
              required>
              {props.products.map((p) => (
                <option key={p.id} value={p.id}>{p.sku} — {p.name}</option>
              ))}
            </select>
          </Field>
          <Field label="Warehouse">
            <select value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}
              required>
              {props.warehouses.map((w) => (
                <option key={w.id} value={w.id}>{w.name}</option>
              ))}
            </select>
          </Field>
          <Field label="Type">
            <select value={type} onChange={(e) => setType(e.target.value)}>
              {TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </Field>
          <Field label={isAdjustment ? "Qty (+/- to correct)" : "Qty"}>
            <input type="number" step="any" value={qty} required
              min={isAdjustment ? undefined : "0.0001"}
              onChange={(e) => setQty(e.target.value)} />
          </Field>
          <Field label={isAdjustment ? "Note (required)" : "Note"}>
            <input value={note} onChange={(e) => setNote(e.target.value)}
              required={isAdjustment}
              placeholder={isAdjustment ? "why the count changed" : "optional"} />
          </Field>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
            <Button variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Posting…" : "Post movement"}
            </Button>
          </div>
        </form>
      </div>
    </div>
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
    <div className="modal-backdrop" onClick={() => props.onDone(false)}>
      <div className="modal card" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 4 }}>Transfer stock</h3>
        <p className="muted" style={{ marginBottom: 16, fontSize: 13 }}>
          Posts a balanced issue + receipt across the two warehouses.
        </p>
        <ErrorNote error={error} />
        {props.warehouses.length < 2 && (
          <p className="muted">Add a second warehouse first.</p>
        )}
        <form onSubmit={submit}>
          <Field label="Product">
            <select value={productId} onChange={(e) => setProductId(e.target.value)}
              required>
              {props.products.map((p) => (
                <option key={p.id} value={p.id}>{p.sku} — {p.name}</option>
              ))}
            </select>
          </Field>
          <Field label="From">
            <select value={from} onChange={(e) => setFrom(e.target.value)} required>
              {props.warehouses.map((w) => (
                <option key={w.id} value={w.id}>{w.name}</option>
              ))}
            </select>
          </Field>
          <Field label="To">
            <select value={to} onChange={(e) => setTo(e.target.value)} required>
              {props.warehouses.map((w) => (
                <option key={w.id} value={w.id}>{w.name}</option>
              ))}
            </select>
          </Field>
          <Field label="Qty">
            <input type="number" step="any" min="0.0001" value={qty} required
              onChange={(e) => setQty(e.target.value)} />
          </Field>
          <Field label="Note">
            <input value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
            <Button variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
            <Button type="submit" disabled={busy || props.warehouses.length < 2}>
              {busy ? "Transferring…" : "Transfer"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
