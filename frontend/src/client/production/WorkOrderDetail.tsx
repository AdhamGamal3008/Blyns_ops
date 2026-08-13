// Work-order detail + the Phase 2 status actions and the read-only pipeline
// mirror. Production never hosts the release approval — it links out to the
// pipeline (docs/PRODUCTION_MODULE_PLAN.md §2.3). Shared by Work Orders + Quality.

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../shared/api";
import {
  Badge, Banner, Button, errorText, Field, Input, Row, Select, Stack,
} from "../../shared/ui";
import { Modal } from "../../shared/ui";
import {
  dueTone, formatDue, formatWindow, type ProjectRollup, sectionLabel,
  type Station, statusLabel, WO_STATUS_TONE, type WorkOrder,
} from "./types";

const REALLOCATABLE = ["queued", "released", "in_progress", "rework"];

export function WorkOrderDetail(props: {
  woId: string;
  canWrite: boolean;
  canManage: boolean;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [wo, setWo] = useState<WorkOrder | null>(null);
  const [rollup, setRollup] = useState<ProjectRollup | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [hours, setHours] = useState("");
  const [rate, setRate] = useState("");
  const [winStart, setWinStart] = useState("");
  const [winEnd, setWinEnd] = useState("");
  const [vehicle, setVehicle] = useState("");
  const [stations, setStations] = useState<Station[]>([]);
  const [stationId, setStationId] = useState("");

  const load = useCallback(() => {
    api<WorkOrder>(`/production/work-orders/${props.woId}`)
      .then((r) => {
        setWo(r.data);
        api<ProjectRollup>(`/production/projects/${r.data.project_id}/rollup`)
          .then((rr) => setRollup(rr.data)).catch(() => setRollup(null));
      })
      .catch(setError);
  }, [props.woId]);
  useEffect(load, [load]);

  useEffect(() => {
    if (!props.canManage) return;
    api<Station[]>("/production/stations").then((r) => setStations(r.data)).catch(() => {});
  }, [props.canManage]);

  async function act(action: string, body?: unknown) {
    setBusy(true);
    setError(null);
    try {
      await api(`/production/work-orders/${props.woId}/${action}`,
        { method: "POST", body: body ?? {} });
      setNote(""); setHours(""); setRate("");
      setWinStart(""); setWinEnd(""); setVehicle("");
      load();
      props.onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const s = wo?.status;
  const w = props.canWrite;

  return (
    <Modal
      open
      onOpenChange={(o) => !o && props.onClose()}
      title={wo?.code ?? "Work order"}
      size="lg"
      footer={<Button onClick={props.onClose}>Close</Button>}
    >
      {!wo ? (
        <p>Loading…</p>
      ) : (
        <Stack gap={3}>
          {error != null && (
            <Banner tone="danger" title="That action failed">{errorText(error)}</Banner>
          )}

          <b>{wo.item_name}</b>
          <Row gap={2}>
            <Badge tone={WO_STATUS_TONE[wo.status] ?? "neutral"}>{statusLabel(wo.status)}</Badge>
            <Badge tone={dueTone(wo.due_date)}>Due {formatDue(wo.due_date)}</Badge>
            {wo.revision_conflict && <Badge tone="danger">revision conflict</Badge>}
            {wo.blocked_by && <Badge tone="warning">blocked: {statusLabel(wo.blocked_by.type)}</Badge>}
          </Row>
          <div>Project: {wo.project_code ?? "—"}{wo.client_name ? ` · ${wo.client_name}` : ""}</div>
          <div>Station: {wo.station_name ?? "Unassigned"}</div>
          <div>Qty: {wo.qty.done} / {wo.qty.ordered}</div>
          <div>
            Drawing:{" "}
            {wo.source_drawing
              ? `${wo.source_drawing.title ?? wo.source_drawing.deliverable_id} · v${wo.source_drawing.version}`
              : "none pinned"}
            {wo.revision_conflict && " — a newer revision has been issued"}
          </div>

          {/* --- status actions (§2.2) --- */}
          <section>
            <b>Actions</b>
            <Stack gap={2}>
              {s === "queued" && (
                <Row gap={2}>
                  <Button onClick={() => act("release")} disabled={busy || !props.canManage}>
                    Release
                  </Button>
                  {!props.canManage && <span>Releasing needs the production_manager role.</span>}
                </Row>
              )}
              {(s === "released" || s === "rework") && (
                <Button onClick={() => act("start")} disabled={busy || !w}>
                  {s === "rework" ? "Resume production" : "Start production"}
                </Button>
              )}
              {s === "in_progress" && (
                <Stack gap={2}>
                  <Row gap={2}>
                    <Field label="Labor hours">
                      <Input type="number" step="any" min="0" value={hours}
                        onChange={(e) => setHours(e.target.value)} />
                    </Field>
                    <Field label="Rate">
                      <Input type="number" step="any" min="0" value={rate}
                        onChange={(e) => setRate(e.target.value)} />
                    </Field>
                  </Row>
                  <Button disabled={busy || !w}
                    onClick={() => act("request-qc",
                      { labor_hours: Number(hours) || 0, labor_rate: Number(rate) || 0 })}>
                    Send to QC
                  </Button>
                </Stack>
              )}
              {s === "qc_pending" && (
                <Stack gap={2}>
                  <Row gap={2}>
                    <Button onClick={() => act("qc", { result: "pass" })} disabled={busy || !w}>
                      Pass QC
                    </Button>
                  </Row>
                  <Field label="Defect / hold note">
                    <Input value={note} onChange={(e) => setNote(e.target.value)}
                      placeholder="What failed?" />
                  </Field>
                  <Button variant="secondary" disabled={busy || !w}
                    onClick={() => act("qc",
                      { result: "hold", defects: note ? [note] : [], note })}>
                    Hold
                  </Button>
                </Stack>
              )}
              {s === "qc_hold" && (
                <Stack gap={2}>
                  {wo.qc?.defects && wo.qc.defects.length > 0 && (
                    <div>Defects: {wo.qc.defects.join(", ")}</div>
                  )}
                  <Field label="Rework note">
                    <Input value={note} onChange={(e) => setNote(e.target.value)} />
                  </Field>
                  <Button disabled={busy || !w} onClick={() => act("rework", { note })}>
                    Route to rework
                  </Button>
                </Stack>
              )}
              {s === "passed" && (
                <Button onClick={() => act("pack")} disabled={busy || !w}>
                  Pack — protection derived from material
                </Button>
              )}
              {s === "packed" && (
                <Stack gap={2}>
                  <Row gap={2}>
                    <Field label="Delivery from">
                      <Input type="datetime-local" value={winStart}
                        onChange={(e) => setWinStart(e.target.value)} />
                    </Field>
                    <Field label="Delivery to">
                      <Input type="datetime-local" value={winEnd}
                        onChange={(e) => setWinEnd(e.target.value)} />
                    </Field>
                  </Row>
                  <Field label="Vehicle" hint="Left blank, it's suggested from the staged load.">
                    <Input value={vehicle} onChange={(e) => setVehicle(e.target.value)}
                      placeholder="Auto from load" />
                  </Field>
                  <Button disabled={busy || !w}
                    onClick={() => act("stage", {
                      delivery_window_start: winStart ? new Date(winStart).toISOString() : null,
                      delivery_window_end: winEnd ? new Date(winEnd).toISOString() : null,
                      vehicle: vehicle || null,
                    })}>
                    Stage for dispatch
                  </Button>
                </Stack>
              )}
              {s === "staged" && (
                <Button onClick={() => act("dispatch")} disabled={busy || !w}>
                  Mark dispatched
                </Button>
              )}
              {s === "dispatched" && (
                <span>Dispatched — this work order has left the building.</span>
              )}

              {(s === "released" || s === "in_progress" || s === "rework") && (
                <Row gap={2}>
                  <Input value={note} onChange={(e) => setNote(e.target.value)}
                    placeholder="Shortfall note" />
                  <Button variant="ghost" disabled={busy || !w || !note}
                    onClick={() => act("shortfall", { note })}>
                    Flag shortfall
                  </Button>
                </Row>
              )}

              {props.canManage && s && REALLOCATABLE.includes(s) && (
                <Row gap={2}>
                  <Select
                    value={stationId}
                    onValueChange={setStationId}
                    options={stations.map((st) => ({
                      value: st.id, label: `${st.code} · ${st.load.work_orders} WO`,
                    }))}
                    placeholder="Reassign station…"
                  />
                  <Button variant="secondary" disabled={busy || !stationId}
                    onClick={() => act("allocate", { station_id: stationId })}>
                    Reassign
                  </Button>
                  <Button variant="ghost" disabled={busy}
                    onClick={() => act("auto-allocate")}>
                    Auto-allocate
                  </Button>
                </Row>
              )}
            </Stack>
          </section>

          {/* --- packing + dispatch record (Phase 4) --- */}
          {(wo.packing || wo.dispatch) && (
            <section>
              <b>Packing & dispatch</b>
              <Stack gap={1}>
                {wo.packing && (
                  <>
                    <div>Packing: {wo.packing.type} · {wo.packing.protection_spec}</div>
                    {wo.packing.moisture_barrier_ref && (
                      <div>Moisture barrier: {wo.packing.moisture_barrier_ref}</div>
                    )}
                    {wo.packing.handling.length > 0 && (
                      <div>Handling: {wo.packing.handling.join(", ")}</div>
                    )}
                  </>
                )}
                {wo.dispatch && (
                  <>
                    <div>
                      Vehicle: {wo.dispatch.vehicle ?? "—"}
                      {wo.dispatch.load ? ` · ${wo.dispatch.load.units} units` : ""}
                    </div>
                    <div>Delivery window: {formatWindow(wo.dispatch.delivery_window)}</div>
                    {wo.dispatch.manifest_ref && (
                      <div>
                        Manifest {wo.dispatch.manifest_ref} · Delivery note{" "}
                        {wo.dispatch.delivery_note_ref}
                      </div>
                    )}
                  </>
                )}
              </Stack>
            </section>
          )}

          {/* --- read-only pipeline mirror + Approve-in-pipeline link (§2.3) --- */}
          {rollup && (
            <section>
              <Row gap={2}>
                <b>Stage 6 · Factory Release</b>
                {rollup.releasable
                  ? <Badge tone="success">ready to release</Badge>
                  : <Badge tone="neutral">in progress</Badge>}
              </Row>
              <Stack gap={1}>
                {rollup.release_checklist.map((sec) => (
                  <Row key={sec} gap={2}>
                    <Badge tone={rollup.checklist_done.includes(sec) ? "success" : "neutral"}>
                      {rollup.checklist_done.includes(sec) ? "done" : "pending"}
                    </Badge>
                    <span>{sectionLabel(sec)}</span>
                    <span>{rollup.sections[sec] ?? 0}%</span>
                  </Row>
                ))}
              </Stack>
              <Link to={`/app/projects/${rollup.project_id}`}>Approve in pipeline →</Link>
            </section>
          )}
        </Stack>
      )}
    </Modal>
  );
}
