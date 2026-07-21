// Versioned deliverables (§3.7, acceptance #6): every revision is appended and
// nothing is overwritten — the UI only ever adds. A `bom` deliverable carries
// product lines that Stage 8 reserves through Inventory.

import { Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import {
  Badge,
  Button,
  CardHeader,
  DataState,
  DataTable,
  type DataTableColumn,
  Field,
  FormModal,
  Input,
  Row,
  Select,
  Stack,
} from "../../shared/ui";
import { humanize, type Deliverable, type DeliverableKind } from "./types";
import styles from "./StagePanel.module.css";

const KINDS: DeliverableKind[] = [
  "shop_drawing", "bom", "scan", "photo", "report", "certificate",
];

export function DeliverablesSection(props: {
  projectId: string; canWrite: boolean; onChanged: () => void;
}) {
  const [items, setItems] = useState<Deliverable[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);
  const [revising, setRevising] = useState<Deliverable | null>(null);

  const load = useCallback(() => {
    setError(null);
    api<Deliverable[]>(`/projects/${props.projectId}/deliverables?page_size=100`)
      .then((r) => setItems(r.data)).catch(setError);
  }, [props.projectId]);

  useEffect(load, [load]);

  const columns: DataTableColumn<Deliverable>[] = [
    { key: "title", header: "Title", sortable: true, accessor: (d) => <b>{d.title}</b>, sortValue: (d) => d.title },
    {
      key: "kind",
      header: "Kind",
      sortable: true,
      accessor: (d) => <Badge tone="neutral">{humanize(d.kind)}</Badge>,
      sortValue: (d) => d.kind,
    },
    { key: "stage_key", header: "Stage", sortable: true, accessor: (d) => humanize(d.stage_key) },
    {
      key: "current_version",
      header: "Version",
      sortable: true,
      accessor: (d) =>
        `v${d.current_version}${d.kind === "bom" && d.lines?.length ? ` · ${d.lines.length} line(s)` : ""}`,
      sortValue: (d) => d.current_version,
    },
    ...(props.canWrite
      ? [{
          key: "actions",
          header: "",
          accessor: (d: Deliverable) => (
            <Button variant="ghost" size="compact" onClick={() => setRevising(d)}>
              Add revision
            </Button>
          ),
        }]
      : []),
  ];

  return (
    <section>
      <CardHeader
        title="Deliverables"
        description="Every revision is appended — versions are never overwritten."
        actions={
          props.canWrite && (
            <Button size="compact" onClick={() => setCreating(true)}>
              <Plus size={15} aria-hidden="true" />
              New deliverable
            </Button>
          )
        }
      />
      <DataState
        loading={!items && !error}
        error={items ? null : error}
        onRetry={load}
        isEmpty={items?.length === 0}
        emptyTitle="No deliverables yet"
        emptyDescription="Shop drawings, BOMs, scans, and certificates land here as the stages progress."
      >
        <DataTable
          data={items ?? []}
          columns={columns}
          getRowId={(d) => d.id}
          searchPlaceholder="Search deliverables…"
        />
      </DataState>

      <DeliverableModal
        open={creating}
        projectId={props.projectId}
        onDone={(ok) => { setCreating(false); if (ok) { load(); props.onChanged(); } }}
      />
      {revising && (
        <RevisionModal projectId={props.projectId} deliverable={revising}
          onDone={(ok) => { setRevising(null); if (ok) load(); }} />
      )}
    </section>
  );
}

const NO_PRODUCT = "__none";

function DeliverableModal(props: {
  open: boolean; projectId: string; onDone: (ok: boolean) => void;
}) {
  const [kind, setKind] = useState<DeliverableKind>("shop_drawing");
  const [title, setTitle] = useState("");
  const [fileRef, setFileRef] = useState("");
  const [lines, setLines] = useState<{ product_id: string; qty: string }[]>(
    [{ product_id: NO_PRODUCT, qty: "" }]);
  const [products, setProducts] = useState<{ id: string; name: string; sku: string }[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!props.open) return;
    api<{ id: string; name: string; sku: string }[]>("/inventory/products?page_size=100")
      .then((r) => setProducts(r.data)).catch(() => setProducts([]));
  }, [props.open]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        kind, title, file_ref: fileRef || `vault://${title}`,
      };
      if (kind === "bom") {
        body.lines = lines
          .filter((l) => l.product_id !== NO_PRODUCT && l.qty)
          .map((l) => ({ product_id: l.product_id, qty: Number(l.qty) }));
      }
      await api(`/projects/${props.projectId}/deliverables`, { method: "POST", body });
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
      title="New deliverable"
      onSubmit={submit}
      error={error}
      errorTitle="Could not create the deliverable"
      busy={busy}
      submitLabel="Create"
    >
      <Field label="Kind">
        <Select
          value={kind}
          onValueChange={(v) => setKind(v as DeliverableKind)}
          options={KINDS.map((k) => ({ value: k, label: humanize(k) }))}
        />
      </Field>
      <Field label="Title" required>
        <Input value={title} onChange={(e) => setTitle(e.target.value)} required />
      </Field>
      <Field label="File reference">
        <Input value={fileRef} onChange={(e) => setFileRef(e.target.value)}
          placeholder="vault://… (optional)" />
      </Field>

      {kind === "bom" && (
        <Stack gap={3}>
          <h4 className={styles.sectionTitle}>BOM lines — reserved from Inventory at Stage 8</h4>
          {lines.map((l, i) => (
            <Row key={i}>
              <Field label="Product" className={styles.grow}>
                <Select
                  value={l.product_id}
                  onValueChange={(v) => {
                    const next = [...lines]; next[i] = { ...l, product_id: v };
                    setLines(next);
                  }}
                  options={[
                    { value: NO_PRODUCT, label: "— select —" },
                    ...products.map((p) => ({ value: p.id, label: `${p.sku} · ${p.name}` })),
                  ]}
                />
              </Field>
              <Field label="Qty" className={styles.grow}>
                <Input type="number" step="any" min="0" value={l.qty} onChange={(e) => {
                  const next = [...lines]; next[i] = { ...l, qty: e.target.value };
                  setLines(next);
                }} />
              </Field>
            </Row>
          ))}
          <div>
            <Button type="button" variant="ghost" size="compact"
              onClick={() => setLines([...lines, { product_id: NO_PRODUCT, qty: "" }])}>
              <Plus size={15} aria-hidden="true" />
              Add line
            </Button>
          </div>
        </Stack>
      )}
    </FormModal>
  );
}

function RevisionModal(props: {
  projectId: string; deliverable: Deliverable; onDone: (ok: boolean) => void;
}) {
  const [fileRef, setFileRef] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api(`/projects/${props.projectId}/deliverables/${props.deliverable.id}/revisions`, {
        method: "POST", body: { file_ref: fileRef || `vault://rev`, note },
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
      title={`Revise ${props.deliverable.title} → v${props.deliverable.current_version + 1}`}
      description="Every version is kept — this appends, it never overwrites."
      onSubmit={submit}
      error={error}
      errorTitle="Could not add the revision"
      busy={busy}
      submitLabel="Add revision"
    >
      <Field label="New file reference">
        <Input value={fileRef} onChange={(e) => setFileRef(e.target.value)} placeholder="vault://…" />
      </Field>
      <Field label="Note">
        <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. clash fix" />
      </Field>
    </FormModal>
  );
}
