// Production Queue (docs/PRODUCTION_MODULE_PLAN.md §6): the cross-project work
// list — every active (not-done) work order within the due window, due-sorted.
// Read-only; the status transitions land in Phase 2.

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import {
  Badge, CardHeader, DataState, DataTable, type DataTableColumn,
} from "../../shared/ui";
import {
  dueTone, formatDue, statusLabel, WO_STATUS_TONE, type WorkOrder,
} from "./types";

export function QueueSection() {
  const [wos, setWos] = useState<WorkOrder[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    api<WorkOrder[]>("/production/queue").then((r) => setWos(r.data)).catch(setError);
  }, []);
  useEffect(load, [load]);

  const columns: DataTableColumn<WorkOrder>[] = [
    {
      key: "code", header: "WO", sortable: true, sortValue: (w) => w.code,
      accessor: (w) => (
        <>
          <b>{w.code}</b>
          <div>{w.item_name}</div>
          {w.revision_conflict && <Badge tone="danger">revision conflict</Badge>}
        </>
      ),
    },
    {
      key: "project", header: "Project / Client",
      accessor: (w) => (
        <>
          <div>{w.project_code ?? "—"}</div>
          {w.client_name && <div>{w.client_name}</div>}
        </>
      ),
    },
    { key: "station", header: "Station", accessor: (w) => w.station_name ?? "Unassigned" },
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
        <Badge tone={WO_STATUS_TONE[w.status] ?? "neutral"}>{statusLabel(w.status)}</Badge>
      ),
    },
    {
      key: "blocked", header: "Blocked by",
      accessor: (w) => (w.blocked_by ? statusLabel(w.blocked_by.type) : "—"),
    },
  ];

  return (
    <section>
      <CardHeader
        title="Queue"
        description={wos ? `${wos.length} active work orders` : "Cross-project work list"}
      />
      <DataState
        loading={!wos && !error}
        error={wos ? null : error}
        onRetry={load}
        isEmpty={wos?.length === 0}
        emptyTitle="Nothing in the queue"
      >
        <DataTable
          data={wos ?? []}
          columns={columns}
          getRowId={(w) => w.id}
          searchPlaceholder="Search work orders…"
        />
      </DataState>
    </section>
  );
}
