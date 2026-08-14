import type { BadgeTone } from "../../shared/ui";

// Shapes for the Project Management module (docs/modules/PROJECT_MANAGEMENT.md).
// The v2.0 stage-gate machine (nine stages): a project holds current_stage_* + a
// timeline of stage instances; each stage carries gates, tasks, and an approval.
// The stage count is never hardcoded — it derives from the timeline/config length.

export interface Budget {
  planned: number;
  committed: number;
  actual: number;
  currency: string;
}

export type WorkflowType = "sequential" | "concurrent";

export interface Project {
  id: string;
  code: string;
  name: string;
  scope?: string | null;
  workflow_type?: WorkflowType;
  crm_account_id?: string | null;
  current_stage_order: number;
  current_stage_key: string;
  status: "active" | "on_hold" | "completed" | "archived" | "cancelled";
  pm_id?: string | null;
  team_ids?: string[];
  budget: Budget;
  stage_history?: { order: number; key: string; result: string }[];
  created_at: string;
}

export interface TimelineStage {
  order: number;
  key: string;
  name: string;
  approver_role?: string | null;
  status: StageStatus;
  entered_at?: string | null;
  recovery_loops: number;
  blocking_reason?: string | null;
}

export interface Timeline {
  project_id: string;
  code: string;
  workflow_type?: WorkflowType;
  current_stage_order: number;
  milestones: { key: string; name: string; due_date: string }[];
  stages: TimelineStage[];
}

export type StageStatus =
  | "pending" | "waiting" | "blocked" | "in_progress" | "validation"
  | "pending_approval" | "approved" | "rejected" | "on_hold";

export interface EntryGate {
  key: string;
  type: "document" | "dependency" | "measurement" | "inspection" | "temporal";
  blocking?: boolean;
  depends_on?: string;
}

export interface StageDefinition {
  order: number;
  key: string;
  name: string;
  entry_gates: EntryGate[];
  automated_tasks: string[];
  quality_gates: string[];
  approver_role?: string | null;
  co_approver_roles?: string[];
  auto_advance?: boolean;               // v2.0 Stage 2 · Site Survey (no approver)
  release_checklist?: string[];         // v2.0 Stage 6 · Factory Release (4 sections)
}

export interface StageInstance {
  id: string;
  status: StageStatus;
  documents_supplied?: string[];
  document_refs?: DocumentRef[];
  checklist_done?: string[];            // v2.0 Stage 6 release-checklist sections done
  waiting_on?: string[];
  blocked_by?: string[];
  task_results?: { task: string; status: string }[];
  recovery_loops: number;
  blocking_reason?: string | null;
}

export interface StageEvaluation {
  waiting_on: string[];
  blocked_by: string[];
  gate_failures: { gate_key: string; reason: string }[];
  severe: boolean;
  ready: boolean;
}

export interface ValidationCheck {
  key: string;
  passed: boolean;
  detail: string;
}

export interface Approval {
  id: string;
  state: "draft" | "auto_validation" | "manager_review" | "approved" | "rejected";
  approver_role?: string | null;
  auto_validation?: { passed: boolean; checks: ValidationCheck[] } | null;
}

export interface GateResult {
  id: string;
  gate_key: string;
  type: string;
  passed: boolean;
  severe: boolean;
  waived?: boolean;                 // v2.0: a director's written waiver (SOP §3)
  reason?: string | null;           // the waiver reason, when waived
  explanation: string;
  captured_at: string;
}

export interface StageDetail {
  definition: StageDefinition;
  instance: StageInstance;
  evaluation: StageEvaluation;
  approval: Approval | null;
  gate_results: GateResult[];
}

export interface GateRule {
  key: string;
  type: "measurement" | "inspection";
  blocking?: boolean;
  attach_to_stages?: string[];
  threshold?: Record<string, unknown>;
  checklist?: string[];
}

/** One row of the Settings-editable approver map (§9): a position resolved to
 *  tenant client roles and/or specific users. Used to tell whether the current
 *  user holds the project_director position (who alone may waive a hard gate). */
export interface ApproverEntry {
  approver_role: string;
  client_roles?: string[];
  assigned_user_ids?: string[];
}

export type DeliverableKind =
  | "shop_drawing" | "bom" | "scan" | "photo" | "report" | "certificate";

export type DeliverableSource = "upload" | "url";

export interface DeliverableVersion {
  v: number;
  source_type: DeliverableSource;
  file_ref: string | null;          // the URL (source=url) or the filename (source=upload)
  file_id?: string | null;          // GridFS id when source=upload
  filename?: string | null;
  content_type?: string | null;
  size?: number | null;
  author_id: string;
  author_name?: string | null;      // resolved server-side
  at: string;
  note: string;
}

export interface Deliverable {
  id: string;
  stage_key: string | null;         // null = a general project document
  gate_key?: string | null;         // set when attached at a stage's document gate
  kind: DeliverableKind;
  title: string;
  current_version: number;
  source_type: DeliverableSource;   // of the latest version
  uploaded_by?: string | null;      // name of the latest version's author
  uploaded_at?: string | null;
  versions: DeliverableVersion[];
  lines?: { product_id: string; qty: number }[];
  immutable_audit: { action: string; by: string; at: string }[];
}

/** The evidence attached to a stage's document gate. `source_type`/`file_ref`
 *  are denormalized so an approver can open it straight from the stage. */
export interface DocumentRef {
  gate_key: string;
  deliverable_id: string;
  title: string;
  version: number;
  source_type: DeliverableSource;
  file_ref: string | null;
  by: string;
  at: string;
}

export type ReportType =
  | "missing_information" | "issue" | "change" | "ncr" | "capa" | "rfi" | "qa" | "na";

export interface Report {
  id: string;
  type: ReportType;
  title: string;
  details: Record<string, unknown>;
  owner_id?: string | null;
  status: "open" | "in_progress" | "resolved" | "closed";
  stage_instance_id?: string | null;
  resolved_at?: string | null;
  created_at: string;
}

export interface JobCost {
  id: string;
  stage_key: string;
  cost_type: "labor" | "material" | "subcontractor" | "machine";
  description?: string | null;
  hours: number;
  quantity: number;
  unit_cost: number;
  amount: number;
  posted_to_finance_ref?: string | null;
  captured_at: string;
}

// --- presentation helpers ----------------------------------------------------

export const STAGE_TONE: Record<StageStatus, BadgeTone> = {
  pending: "neutral",
  waiting: "warning",
  blocked: "warning",
  in_progress: "info",
  validation: "info",
  pending_approval: "brand",
  approved: "success",
  rejected: "danger",
  on_hold: "danger",
};

export const PROJECT_TONE: Record<Project["status"], BadgeTone> = {
  active: "success",
  on_hold: "danger",
  completed: "success",
  archived: "neutral",
  cancelled: "danger",
};

export const REPORT_TONE: Record<string, BadgeTone> = {
  open: "danger",
  in_progress: "warning",
  resolved: "success",
  closed: "neutral",
};

export function money(n: number, currency = "USD"): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency", currency, maximumFractionDigits: 2,
  }).format(n ?? 0);
}

/** Humanize a snake_case key ("site_measurement_verification" → "Site measurement verification").
 *  Null-safe: a legacy/partial doc missing the field renders as "—" rather than
 *  throwing and blanking the whole view. */
export function humanize(key?: string | null): string {
  if (!key) return "—";
  const s = key.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}
