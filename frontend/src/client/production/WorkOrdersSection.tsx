// Work-order register + the D4 generation flow (auto-propose from a project BOM,
// production_manager confirms). Read for anyone with production access; the
// Generate action is manager-only (docs/PRODUCTION_MODULE_PLAN.md §6, D4).

import { Eye, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import {
  Badge, Banner, Button, CardHeader, Combobox, DataState, DataTable,
  type DataTableColumn, errorText, Field, Modal, Row, Stack,
} from "../../shared/ui";
import {
  dueTone, formatDue, statusLabel, WO_STATUS_TONE,
  type WorkOrder, type WorkOrderDraft,
} from "./types";
import { WorkOrderDetail } from "./WorkOrderDetail";

interface ProjectRow {
  id: string;
  code: string;
  name: string;
}

export function WorkOrdersSection(props: { canWrite: boolean; canManage: boolean }) {
  const [wos, setWos] = useState<WorkOrder[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [generating, setGenerating] = useState(false);
  const [viewing, setViewing] = useState<WorkOrder | null>(null);

  const load = useCallback(() => {
    api<WorkOrder[]>("/production/work-orders?page_size=100")
      .then((r) => setWos(r.data)).catch(setError);
  }, []);
  useEffect(load, [load]);

  const columns: DataTableColumn<WorkOrder>[] = [
    {
      key: "code", header: "WO", sortable: true, sortValue: (w) => w.code,
      accessor: (w) => (<><b>{w.code}</b><div>{w.item_name}</div></>),
    },
    { key: "project", header: "Project", accessor: (w) => w.project_code ?? "—" },
    {
      key: "qty", header: "Qty", numeric: true,
      accessor: (w) => `${w.qty.done} / ${w.qty.ordered}`,
    },
    {
      key: "due", header: "Due", sortable: true, sortValue: (w) => w.due_date ?? "",
      accessor: (w) => <Badge tone={dueTone(w.due_date)}>{formatDue(w.due_date)}</Badge>,
    },
    {
      key: "status", header: "Status", sortable: true, sortValue: (w) => w.status,
      accessor: (w) => (
        <Row gap={2}>
          <Badge tone={WO_STATUS_TONE[w.status] ?? "neutral"}>{statusLabel(w.status)}</Badge>
          {w.revision_conflict && <Badge tone="danger">rev conflict</Badge>}
        </Row>
      ),
    },
    {
      key: "actions", header: "",
      accessor: (w) => (
        <Button variant="ghost" size="compact" onClick={() => setViewing(w)}>
          <Eye size={14} aria-hidden="true" /> View
        </Button>
      ),
    },
  ];

  return (
    <section>
      <CardHeader
        title="Work Orders"
        description={wos ? `${wos.length} in the register` : "Work-order register"}
        actions={props.canManage && (
          <Button size="compact" onClick={() => setGenerating(true)}>
            <Plus size={15} aria-hidden="true" /> Generate work orders
          </Button>
        )}
      />

      {error != null && wos != null && (
        <Banner tone="danger" title="That action failed">{errorText(error)}</Banner>
      )}

      <DataState
        loading={!wos && !error}
        error={wos ? null : error}
        onRetry={load}
        isEmpty={wos?.length === 0}
        emptyTitle="No work orders yet"
      >
        <DataTable data={wos ?? []} columns={columns} getRowId={(w) => w.id}
          searchPlaceholder="Search work orders…" />
      </DataState>

      {generating && (
        <GenerateModal onDone={(ok) => { setGenerating(false); if (ok) load(); }} />
      )}
      {viewing && (
        <WorkOrderDetail
          woId={viewing.id}
          canWrite={props.canWrite}
          canManage={props.canManage}
          onClose={() => setViewing(null)}
          onChanged={load}
        />
      )}
    </section>
  );
}

/** Auto-propose one draft WO per BOM line, review, then confirm (D4). Nothing is
 *  created until the manager confirms. */
function GenerateModal(props: { onDone: (ok: boolean) => void }) {
  const [projects, setProjects] = useState<ProjectRow[]>([]);
  const [projectId, setProjectId] = useState("");
  const [drafts, setDrafts] = useState<WorkOrderDraft[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<ProjectRow[]>("/projects?page_size=100")
      .then((r) => setProjects(r.data)).catch(() => setProjects([]));
  }, []);

  async function propose(id: string) {
    setProjectId(id);
    setDrafts(null);
    setError(null);
    if (!id) return;
    setBusy(true);
    try {
      const r = await api<WorkOrderDraft[]>("/production/work-orders/propose",
        { method: "POST", body: { project_id: id } });
      setDrafts(r.data);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!drafts?.length) return;
    setBusy(true);
    setError(null);
    try {
      await api("/production/work-orders", { method: "POST", body: { work_orders: drafts } });
      props.onDone(true);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  const count = drafts?.length ?? 0;

  return (
    <Modal
      open
      onOpenChange={(o) => !o && props.onDone(false)}
      title="Generate work orders"
      size="lg"
      footer={
        <Row gap={2}>
          <Button variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
          <Button onClick={confirm} disabled={busy || count === 0}>
            {count > 0 ? `Create ${count} work order${count > 1 ? "s" : ""}` : "Create work orders"}
          </Button>
        </Row>
      }
    >
      <Stack gap={3}>
        {error != null && (
          <Banner tone="danger" title="Could not generate">{errorText(error)}</Banner>
        )}
        <Field label="Project" hint="Auto-proposes one work order per BOM line, pinned to the current shop-drawing revision.">
          <Combobox
            options={projects.map((p) => ({ value: p.id, label: `${p.code} · ${p.name}` }))}
            value={projectId}
            onValueChange={propose}
            placeholder="Choose a project…"
          />
        </Field>

        {drafts && drafts.length > 0 && (
          <table>
            <thead>
              <tr><th align="left">Item</th><th align="right">Qty</th><th align="left">Drawing</th><th align="left">Due</th></tr>
            </thead>
            <tbody>
              {drafts.map((d, i) => (
                <tr key={i}>
                  <td>{d.item_name}</td>
                  <td align="right">{d.qty_ordered}</td>
                  <td>{d.source_drawing ? `v${d.source_drawing.version}` : "—"}</td>
                  <td>{formatDue(d.due_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {drafts && drafts.length === 0 && <p>No work orders were proposed for this project.</p>}
      </Stack>
    </Modal>
  );
}
