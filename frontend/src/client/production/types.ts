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
