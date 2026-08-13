// Quality register (docs/PRODUCTION_MODULE_PLAN.md §6): work orders awaiting QC,
// on hold, or reworking. A QC hold blocks only its own WO — never the project.

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import {
  Badge, Button, CardHeader, DataState, DataTable, type DataTableColumn,
} from "../../shared/ui";
import { QC_STATUSES, statusLabel, WO_STATUS_TONE, type WorkOrder } from "./types";
import { WorkOrderDetail } from "./WorkOrderDetail";

export function QualitySection(props: { canWrite: boolean; canManage: boolean }) {
  const [wos, setWos] = useState<WorkOrder[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [viewing, setViewing] = useState<WorkOrder | null>(null);

  const load = useCallback(() => {
    api<WorkOrder[]>("/production/work-orders?page_size=100")
      .then((r) => setWos(r.data.filter((w) => QC_STATUSES.includes(w.status))))
      .catch(setError);
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
    {
      key: "defects", header: "Defects",
      accessor: (w) => (w.qc?.defects?.length ? w.qc.defects.join(", ") : "—"),
    },
    {
      key: "actions", header: "",
      accessor: (w) => (
        <Button variant="ghost" size="compact" onClick={() => setViewing(w)}>Review</Button>
      ),
    },
  ];

  return (
    <section>
      <CardHeader
        title="Quality"
        description={wos ? `${wos.length} in QC, hold, or rework` : "Defect, hold & rework register"}
      />
      <DataState
        loading={!wos && !error}
        error={wos ? null : error}
        onRetry={load}
        isEmpty={wos?.length === 0}
        emptyTitle="Nothing in QC"
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
    </section>
  );
}
