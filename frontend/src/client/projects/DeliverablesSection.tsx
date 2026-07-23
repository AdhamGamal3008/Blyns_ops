// The project's Documents hub (§3.7): the team uploads any related doc — a real
// file (stored self-hosted in GridFS) or a URL reference — and every document
// records who added it, how, which stage it belongs to (or "general"), and
// when. Versioned: every revision is appended, nothing is overwritten. A `bom`
// document still carries the product lines Stage 8 reserves through Inventory.

import { Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, apiDownload, apiUpload } from "../../shared/api";
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
  Stack,
} from "../../shared/ui";
import {
  humanize,
  type Deliverable,
  type DeliverableKind,
  type DeliverableSource,
  type DeliverableVersion,
} from "./types";
import styles from "./StagePanel.module.css";

const KINDS: DeliverableKind[] = [
  "shop_drawing", "bom", "scan", "photo", "report", "certificate",
];
const GENERAL = "__general"; // sentinel: a document not tied to any stage

function kindLabel(kind: string): string {
  return kind === "bom" ? "BOM" : humanize(kind);
}
function latestOf(d: Deliverable): DeliverableVersion | undefined {
  return d.versions?.[d.versions.length - 1];
}
function isHttp(s?: string | null): boolean {
  return !!s && /^https?:\/\//i.test(s);
}
function fmtDate(s?: string | null): string {
  return s ? new Date(s).toLocaleDateString() : "—";
}

export function DeliverablesSection(props: {
  projectId: string; canWrite: boolean; currentStageKey?: string | null;
  onChanged: () => void;
}) {
  const [items, setItems] = useState<Deliverable[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);
  const [revising, setRevising] = useState<Deliverable | null>(null);

  const load = useCallback(() => {
    setError(null);
    api<Deliverable[]>(`/projects/${props.projectId}/deliverables?page_size=100`)
      .then((r) => setItems(r.data)).catch(setError);
  }, [props.projectId]);

  useEffect(load, [load]);

  async function download(d: Deliverable) {
    setActionError(null);
    try {
      await apiDownload(
        `/projects/${props.projectId}/deliverables/${d.id}/download`,
        latestOf(d)?.filename ?? d.title,
      );
    } catch (e) {
      setActionError(e);
    }
  }

  const columns: DataTableColumn<Deliverable>[] = [
    { key: "title", header: "Title", sortable: true, accessor: (d) => <b>{d.title}</b>, sortValue: (d) => d.title },
    {
      key: "kind", header: "Kind", sortable: true,
      accessor: (d) => <Badge tone="neutral">{kindLabel(d.kind)}</Badge>,
      sortValue: (d) => d.kind,
    },
    {
      key: "stage_key", header: "Stage", sortable: true,
      accessor: (d) => (d.stage_key ? humanize(d.stage_key) : <span className={styles.note}>General</span>),
      sortValue: (d) => d.stage_key ?? "",
    },
    {
      key: "uploaded_by", header: "Added by", sortable: true,
      accessor: (d) => d.uploaded_by ?? "—", sortValue: (d) => d.uploaded_by ?? "",
    },
    {
      key: "source", header: "Source", sortable: true,
      accessor: (d) => <Badge tone={d.source_type === "upload" ? "info" : "neutral"}>
        {d.source_type === "upload" ? "File" : "URL"}
      </Badge>,
      sortValue: (d) => d.source_type,
    },
    {
      key: "current_version", header: "Version", sortable: true,
      accessor: (d) =>
        `v${d.current_version}${d.kind === "bom" && d.lines?.length ? ` · ${d.lines.length} line(s)` : ""}`,
      sortValue: (d) => d.current_version,
    },
    { key: "uploaded_at", header: "Updated", sortable: true, accessor: (d) => fmtDate(d.uploaded_at), sortValue: (d) => d.uploaded_at ?? "" },
    {
      key: "actions", header: "",
      accessor: (d) => {
        const v = latestOf(d);
        return (
          <Row gap={1}>
            {d.source_type === "upload" ? (
              <Button variant="ghost" size="compact" onClick={() => download(d)}>Download</Button>
            ) : isHttp(v?.file_ref) ? (
              <a className={styles.refLink} href={v!.file_ref!} target="_blank" rel="noreferrer">Open</a>
            ) : (
              <span className={styles.note}>{v?.file_ref}</span>
            )}
            {props.canWrite && (
              <Button variant="ghost" size="compact" onClick={() => setRevising(d)}>Revise</Button>
            )}
          </Row>
        );
      },
    },
  ];

  return (
    <section>
      <CardHeader
        title="Documents"
        description="Any file or link the team needs for this project — uploaded or referenced, versioned, and attributable."
        actions={
          props.canWrite && (
            <Button size="compact" onClick={() => setCreating(true)}>
              <Plus size={15} aria-hidden="true" />
              New document
            </Button>
          )
        }
      />
      {actionError != null && (
        <Banner tone="danger" title="That action failed" onDismiss={() => setActionError(null)}>
          {errorText(actionError)}
        </Banner>
      )}
      <DataState
        loading={!items && !error}
        error={items ? null : error}
        onRetry={load}
        isEmpty={items?.length === 0}
        emptyTitle="No documents yet"
        emptyDescription="Upload a file or add a link — drawings, BOMs, scans, certificates, or anything the team needs."
      >
        <DataTable
          data={items ?? []}
          columns={columns}
          getRowId={(d) => d.id}
          searchPlaceholder="Search documents…"
        />
      </DataState>

      <DocumentModal
        open={creating}
        projectId={props.projectId}
        currentStageKey={props.currentStageKey}
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
const SOURCES: { value: DeliverableSource; label: string }[] = [
  { value: "upload", label: "Upload a file" },
  { value: "url", label: "Reference a URL" },
];

/** Upload a file (to GridFS) or record a URL, returning the source fields the
 *  create/revise endpoints expect. Throws on a missing/invalid choice. */
async function resolveSource(
  projectId: string, source: DeliverableSource, file: File | null, url: string,
): Promise<{ source_type: DeliverableSource; file_id?: string; file_ref?: string }> {
  if (source === "upload") {
    if (!file) throw new Error("Choose a file to upload.");
    const up = await apiUpload<{ file_id: string }>(
      `/projects/${projectId}/deliverables/files`, file);
    return { source_type: "upload", file_id: up.data.file_id };
  }
  if (!url.trim()) throw new Error("Enter a URL to reference.");
  return { source_type: "url", file_ref: url.trim() };
}

function DocumentModal(props: {
  open: boolean; projectId: string; currentStageKey?: string | null;
  onDone: (ok: boolean) => void;
}) {
  const [kind, setKind] = useState<DeliverableKind>("shop_drawing");
  const [title, setTitle] = useState("");
  const [source, setSource] = useState<DeliverableSource>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [stageKey, setStageKey] = useState<string>(props.currentStageKey || GENERAL);
  const [stages, setStages] = useState<{ key: string; name: string }[]>([]);
  const [lines, setLines] = useState<{ product_id: string; qty: string }[]>(
    [{ product_id: NO_PRODUCT, qty: "" }]);
  const [products, setProducts] = useState<{ id: string; name: string; sku: string }[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!props.open) return;
    setStageKey(props.currentStageKey || GENERAL);
    api<{ key: string; name: string }[]>("/projects/config/stages")
      .then((r) => setStages(r.data)).catch(() => setStages([]));
    api<{ id: string; name: string; sku: string }[]>("/inventory/products?page_size=100")
      .then((r) => setProducts(r.data)).catch(() => setProducts([]));
  }, [props.open, props.currentStageKey]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const src = await resolveSource(props.projectId, source, file, url);
      const body: Record<string, unknown> = {
        kind, title, ...src,
        stage_key: stageKey === GENERAL ? null : stageKey,
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
      title="New document"
      onSubmit={submit}
      error={error}
      errorTitle="Could not add the document"
      busy={busy}
      submitLabel="Add document"
    >
      <Field label="Title" required>
        <Input value={title} onChange={(e) => setTitle(e.target.value)} required />
      </Field>
      <Row>
        <Field label="Kind" className={styles.grow}>
          <Select value={kind} onValueChange={(v) => setKind(v as DeliverableKind)}
            options={KINDS.map((k) => ({ value: k, label: kindLabel(k) }))} />
        </Field>
        <Field label="Stage" className={styles.grow}>
          <Select value={stageKey} onValueChange={setStageKey}
            options={[
              { value: GENERAL, label: "General (no stage)" },
              ...stages.map((s) => ({ value: s.key, label: s.name })),
            ]} />
        </Field>
      </Row>

      <Field label="Source">
        <Select value={source} onValueChange={(v) => setSource(v as DeliverableSource)}
          options={SOURCES} />
      </Field>
      {source === "upload" ? (
        <Field label="File" required>
          <input className={styles.fileInput} type="file"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </Field>
      ) : (
        <Field label="URL" required>
          <Input value={url} onChange={(e) => setUrl(e.target.value)}
            placeholder="https://…" />
        </Field>
      )}

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
  const [source, setSource] = useState<DeliverableSource>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const src = await resolveSource(props.projectId, source, file, url);
      await api(`/projects/${props.projectId}/deliverables/${props.deliverable.id}/revisions`, {
        method: "POST", body: { ...src, note },
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
      <Field label="Source">
        <Select value={source} onValueChange={(v) => setSource(v as DeliverableSource)}
          options={SOURCES} />
      </Field>
      {source === "upload" ? (
        <Field label="File" required>
          <input className={styles.fileInput} type="file"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </Field>
      ) : (
        <Field label="URL" required>
          <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" />
        </Field>
      )}
      <Field label="Note">
        <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. clash fix" />
      </Field>
    </FormModal>
  );
}
