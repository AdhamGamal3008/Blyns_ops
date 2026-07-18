// Shapes for the Project Management module (docs/modules/PROJECT_MANAGEMENT.md).
// The 16-stage stage-gate machine: a project holds current_stage_* + a timeline
// of stage instances; each stage carries gates, tasks, and an approval.

export interface Budget {
  planned: number;
  committed: number;
  actual: number;
  currency: string;
}

export interface Project {
  id: string;
  code: string;
  name: string;
  scope?: string | null;
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
}

export interface StageInstance {
  id: string;
  status: StageStatus;
  documents_supplied?: string[];
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

export type DeliverableKind =
  | "shop_drawing" | "bom" | "scan" | "photo" | "report" | "certificate";

export interface Deliverable {
  id: string;
  stage_key: string;
  kind: DeliverableKind;
  title: string;
  current_version: number;
  versions: { v: number; file_ref: string; author_id: string; at: string; note: string }[];
  lines?: { product_id: string; qty: number }[];
  immutable_audit: { action: string; by: string; at: string }[];
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

export const STAGE_TONE: Record<StageStatus, string> = {
  pending: "neutral",
  waiting: "warn",
  blocked: "warn",
  in_progress: "neutral",
  validation: "neutral",
  pending_approval: "warn",
  approved: "ok",
  rejected: "danger",
  on_hold: "danger",
};

export const PROJECT_TONE: Record<Project["status"], string> = {
  active: "ok",
  on_hold: "danger",
  completed: "ok",
  archived: "neutral",
  cancelled: "danger",
};

export const REPORT_TONE: Record<string, string> = {
  open: "danger",
  in_progress: "warn",
  resolved: "ok",
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
