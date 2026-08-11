// Production module types + presentational helpers
// (docs/PRODUCTION_MODULE_PLAN.md §2–3).

import type { BadgeTone } from "../../shared/ui";

export interface WorkOrderLine {
  product_id: string;
  sku?: string | null;
  description?: string | null;
  qty: number;
  uom?: string | null;
}

export interface SourceDrawing {
  deliverable_id: string;
  title?: string | null;
  version: number;
}

export interface BlockedBy {
  type: string;
  note?: string | null;
}

export interface WorkOrder {
  id: string;
  code: string;
  project_id: string;
  project_code?: string | null;
  client_name?: string | null;
  item_name: string;
  source_drawing?: SourceDrawing | null;
  bom_lines: WorkOrderLine[];
  qty: { ordered: number; done: number };
  station_route: string[];
  current_station_id?: string | null;
  station_name?: string | null;
  assigned_function?: string | null;
  due_date?: string | null;
  status: string;
  blocked_by?: BlockedBy | null;
  revision_conflict?: boolean;
  qc?: { result: string; defects: string[]; note?: string | null } | null;
}

/** The propose output; the identical shape is posted back to confirm (D4). */
export interface WorkOrderDraft {
  project_id: string;
  item_name: string;
  source_drawing?: SourceDrawing | null;
  bom_lines: WorkOrderLine[];
  qty_ordered: number;
  station_id?: string | null;
  due_date?: string | null;
}

export const WO_STATUS_TONE: Record<string, BadgeTone> = {
  queued: "neutral", released: "info", in_progress: "info",
  qc_pending: "warning", qc_hold: "danger", rework: "warning",
  passed: "success", packed: "success", staged: "success", dispatched: "brand",
};

export function statusLabel(value: string): string {
  return value.replace(/_/g, " ");
}

/** Red past due, amber within 48h (plan §3). */
export function dueTone(due?: string | null): BadgeTone {
  if (!due) return "neutral";
  const ms = new Date(due).getTime() - Date.now();
  if (ms < 0) return "danger";
  if (ms < 48 * 3600 * 1000) return "warning";
  return "neutral";
}

export function formatDue(due?: string | null): string {
  if (!due) return "—";
  return new Date(due).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export interface Station {
  id: string;
  code: string;
  name: string;
  material_types: string[];
  capacity_units_per_day: number;
  is_active: boolean;
  load: {
    units: number;
    work_orders: number;
    capacity: number;
    utilization: number | null;
  };
}

/** The read-only Stage-6 mirror Production shows next to "Approve in pipeline". */
export interface ProjectRollup {
  project_id: string;
  project_code?: string | null;
  sections: Record<string, number>;
  release_checklist: string[];
  checklist_done: string[];
  stage_order?: number | null;
  stage_status?: string | null;
  releasable: boolean;
}

/** WOs that belong in the Quality register — awaiting QC, held, or reworking. */
export const QC_STATUSES = ["qc_pending", "qc_hold", "rework"];

export function sectionLabel(section: string): string {
  return section.replace(/_/g, " ");
}
