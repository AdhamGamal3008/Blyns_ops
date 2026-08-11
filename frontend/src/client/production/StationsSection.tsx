// Stations (docs/PRODUCTION_MODULE_PLAN.md §6): load and capacity by work centre.
// Read-only — reallocation happens on a work order in its detail (manager-gated).

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import {
  Badge, type BadgeTone, CardHeader, DataState, DataTable, type DataTableColumn,
} from "../../shared/ui";
import type { Station } from "./types";

function utilTone(u: number | null): BadgeTone {
  if (u == null) return "neutral";
  if (u >= 100) return "danger";
  if (u >= 80) return "warning";
  return "success";
}

export function StationsSection() {
  const [stations, setStations] = useState<Station[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    api<Station[]>("/production/stations").then((r) => setStations(r.data)).catch(setError);
  }, []);
  useEffect(load, [load]);

  const columns: DataTableColumn<Station>[] = [
    {
      key: "name", header: "Work centre", sortable: true, sortValue: (s) => s.name,
      accessor: (s) => (<><b>{s.name}</b><div>{s.code}</div></>),
    },
    {
      key: "material", header: "Materials",
      accessor: (s) => (s.material_types.length ? s.material_types.join(", ") : "any"),
    },
    {
      key: "wos", header: "Work orders", numeric: true,
      sortable: true, sortValue: (s) => s.load.work_orders,
      accessor: (s) => s.load.work_orders,
    },
    {
      key: "load", header: "Load / capacity", numeric: true,
      accessor: (s) => `${s.load.units} / ${s.load.capacity || "—"}`,
    },
    {
      key: "util", header: "Utilization", sortable: true,
      sortValue: (s) => s.load.utilization ?? -1,
      accessor: (s) => (s.load.utilization == null
        ? "—"
        : <Badge tone={utilTone(s.load.utilization)}>{s.load.utilization}%</Badge>),
    },
  ];

  return (
    <section>
      <CardHeader
        title="Stations"
        description={stations ? `${stations.length} work centres` : "Load and capacity by work centre"}
      />
      <DataState
        loading={!stations && !error}
        error={stations ? null : error}
        onRetry={load}
        isEmpty={stations?.length === 0}
        emptyTitle="No stations configured"
      >
        <DataTable data={stations ?? []} columns={columns} getRowId={(s) => s.id}
          searchPlaceholder="Search stations…" />
      </DataState>
    </section>
  );
}
