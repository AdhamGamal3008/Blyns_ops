// Tenant-defined project configurations (docs/PROJECT_CONFIGURATIONS_PLAN.md).
// A configuration is a named, versioned set of the 9 stages' entry documents,
// quality gates and thresholds, plus the workflow shape. Editing publishes a new
// immutable version; projects pin the version current when they were created.

export type WorkflowShape = "sequential" | "concurrent";

export interface ProjectConfiguration {
  id: string;
  name: string;
  description?: string;
  workflow_shape: WorkflowShape;
  current_version: number;
  is_system: boolean;
  is_default: boolean;
  is_active: boolean;
}

/** One entry gate on a stage. `document` gates are tenant-editable; `dependency`
 *  gates encode the workflow shape and are derived, never edited here. */
export interface EntryGate {
  key: string;
  type: "document" | "dependency";
  label?: string;
  blocking?: boolean;
  depends_on?: string;
}

export interface StageDefinition {
  id: string;
  key: string;
  order: number;
  name: string;
  approver_role: string | null;
  entry_gates?: EntryGate[];
  quality_gates?: string[];
}

export type Threshold = Record<string, string | number | boolean>;

export interface GateRule {
  id: string;
  key: string;
  type?: string;
  blocking?: boolean;
  threshold?: Threshold;
  severe_threshold?: Threshold;
  checklist?: string[];
}

export interface GateCatalogEntry {
  id: string;
  key: string;
  name: string;
  type: "measurement" | "inspection";
  blocking?: boolean;
  threshold?: Threshold;
  checklist?: string[];
  is_builtin?: boolean;
}

/** `GET /projects/config/configurations/{id}` — the editor's load. */
export interface ConfigurationDetail extends ProjectConfiguration {
  stages: StageDefinition[];
  gates: GateRule[];
}

/** `POST /projects/config/configurations/{id}/versions` — the editor's save. */
export interface VersionPublish {
  workflow_shape?: WorkflowShape;
  stages: {
    key: string;
    entry_documents: { key: string; label?: string; blocking: boolean }[];
    quality_gates: string[];
  }[];
  gates: {
    key: string;
    threshold?: Threshold;
    blocking?: boolean;
    checklist?: string[];
  }[];
}

export const SHAPE_LABEL: Record<WorkflowShape, string> = {
  sequential: "Sequential",
  concurrent: "Concurrent",
};

export const SHAPE_HINT: Record<WorkflowShape, string> = {
  sequential: "Each stage opens when the one before it is approved.",
  concurrent:
    "Stages 2–8 open together off Stage 1 and run in parallel; Stage 9 waits for all.",
};

/** `timber_moisture_content` → `Timber moisture content`. Mirrors the backend's
 *  `seed.gate_label`, used for gates and documents that carry no label. */
export function humanize(key: string): string {
  const words = key.replace(/_/g, " ").trim();
  return words ? words[0].toUpperCase() + words.slice(1) : key;
}
