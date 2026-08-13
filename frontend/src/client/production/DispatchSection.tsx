// Dispatch board (docs/PRODUCTION_MODULE_PLAN.md §6): work orders moving through
// packed → staged → shipped, with the generated shipping manifest. The pack /
// stage / dispatch actions live in the work-order detail (shared with Quality).

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import {
  Badge, Button, CardHeader, DataState, DataTable, type DataTableColumn,
  Modal, Row, Stack,
} from "../../shared/ui";
import {
  formatWindow, type Manifest, statusLabel, WO_STATUS_TONE, type WorkOrder,
} from "./types";
import { WorkOrderDetail } from "./WorkOrderDetail";

export function DispatchSection(props: { canWrite: boolean; canManage: boolean }) {
  const [wos, setWos] = useState<WorkOrder[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [viewing, setViewing] = useState<WorkOrder | null>(null);
  const [manifestOf, setManifestOf] = useState<WorkOrder | null>(null);

  const load = useCallback(() => {
    api<WorkOrder[]>("/production/dispatch").then((r) => setWos(r.data)).catch(setError);
  }, []);
  useEffect(load, [load]);

  const columns: DataTableColumn<WorkOrder>[] = [
    {
      key: "code", header: "WO", sortable: true, sortValue: (w) => w.code,
      accessor: (w) => (<><b>{w.code}</b><div>{w.item_name}</div></>),
    },
    { key: "project", header: "Project", accessor: (w) => w.project_code ?? "—" },
    {
      key: "status", header: "Status", sortable: true, sortValue: (w) => w.status,
      accessor: (w) => (
        <Badge tone={WO_STATUS_TONE[w.status] ?? "neutral"}>{statusLabel(w.status)}</Badge>
      ),
    },
    { key: "vehicle", header: "Vehicle", accessor: (w) => w.dispatch?.vehicle ?? "—" },
    {
      key: "window", header: "Delivery window",
      accessor: (w) => formatWindow(w.dispatch?.delivery_window),
    },
    {
      key: "actions", header: "",
      accessor: (w) => (
        <Row gap={2}>
          <Button variant="ghost" size="compact" onClick={() => setViewing(w)}>Open</Button>
          <Button variant="ghost" size="compact" disabled={!w.dispatch?.manifest_ref}
            onClick={() => setManifestOf(w)}>Manifest</Button>
        </Row>
      ),
    },
  ];

  return (
    <section>
      <CardHeader
        title="Dispatch"
        description={wos
          ? `${wos.length} packed, staged, or shipped`
          : "Packed → staged → shipped, with manifest"}
      />
      <DataState
        loading={!wos && !error}
        error={wos ? null : error}
        onRetry={load}
        isEmpty={wos?.length === 0}
        emptyTitle="Nothing to dispatch yet"
      >
        <DataTable data={wos ?? []} columns={columns} getRowId={(w) => w.id}
          searchPlaceholder="Search work orders…" />
      </DataState>
      {viewing && (
        <WorkOrderDetail
          woId={viewing.id}
          canWrite={props.canWrite}
          canManage={props.canManage}
          onClose={() => setViewing(null)}
          onChanged={load}
        />
      )}
      {manifestOf && (
        <ManifestModal woId={manifestOf.id} onClose={() => setManifestOf(null)} />
      )}
    </section>
  );
}

/** The generated shipping manifest — packing spec, dispatch details, line items. */
function ManifestModal(props: { woId: string; onClose: () => void }) {
  const [m, setM] = useState<Manifest | null>(null);

  useEffect(() => {
    api<Manifest>(`/production/work-orders/${props.woId}/manifest`)
      .then((r) => setM(r.data)).catch(() => setM(null));
  }, [props.woId]);

  return (
    <Modal
      open
      onOpenChange={(o) => !o && props.onClose()}
      title={m ? `Manifest ${m.manifest_ref ?? m.work_order}` : "Manifest"}
      size="lg"
      footer={<Button onClick={props.onClose}>Close</Button>}
    >
      {!m ? (
        <p>Loading…</p>
      ) : (
        <Stack gap={3}>
          <div>
            <b>{m.item_name}</b>
            <div>{m.project_code}{m.client_name ? ` · ${m.client_name}` : ""}</div>
          </div>
          <Row gap={3}>
            <div>Delivery note: {m.delivery_note_ref ?? "—"}</div>
            <div>Vehicle: {m.dispatch?.vehicle ?? "—"}</div>
          </Row>
          <div>Delivery window: {formatWindow(m.dispatch?.delivery_window)}</div>
          {m.packing && (
            <div>
              Packed as {m.packing.type} · {m.packing.protection_spec}
              {m.packing.moisture_barrier_ref ? ` · ${m.packing.moisture_barrier_ref}` : ""}
            </div>
          )}
          <table>
            <thead>
              <tr>
                <th align="left">Item</th>
                <th align="right">Qty</th>
                <th align="left">UoM</th>
              </tr>
            </thead>
            <tbody>
              {m.lines.map((l, i) => (
                <tr key={i}>
                  <td>{l.description ?? l.sku ?? l.product_id}</td>
                  <td align="right">{l.qty}</td>
                  <td>{l.uom ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Stack>
      )}
    </Modal>
  );
}
