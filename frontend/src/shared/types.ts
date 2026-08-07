// Shared API types (JSON fields snake_case per docs/BUILD.md §5; TS types PascalCase).

export interface Envelope<T> {
  data: T;
  meta?: Record<string, unknown>;
}

export interface Tokens {
  access_token: string;
  refresh_token: string;
}

export type Realm = "client" | "admin";

export type PermissionLevel = 0 | 1 | 2 | 3; // NONE | VIEW | READ | WRITE

/** Per-tab CSV grants (docs/modules/SETTINGS.md §1.3): each list holds
 *  `"{module}:{entity}"` keys the role may export / import / approve-import.
 *  Layered on module READ; `approve_import` implies import. */
export interface CsvAccess {
  export: string[];
  import: string[];
  approve_import: string[];
}

export interface RoleInfo {
  id: string;
  name: string;
  permissions: Record<string, PermissionLevel>;
  /** Effective grants — present on the client `/me` role, absent for admins. */
  csv_access?: CsvAccess;
}

/** One import/export tab, from `GET /settings/csv-catalog` — drives the role
 *  editor's grant multi-selects. `importable` is false for a derived, export-only
 *  view (Inventory stock levels), which the import/approve selects omit. */
export interface CsvCatalogEntry {
  key: string;
  module: string;
  entity: string;
  label: string;
  importable: boolean;
}

/** A staged import awaiting approval (docs/modules/SETTINGS.md §1.3). */
export interface ImportRequest {
  id: string;
  module: string;
  entity: string;
  status: "pending" | "approved" | "rejected";
  filename: string | null;
  requested_by: string | null;
  requested_by_name: string | null;
  requested_at: string | null;
  preview: ImportRequestCounts;
  decided_by_name?: string | null;
  decided_at?: string | null;
  reject_reason?: string | null;
  result?: ImportRequestCounts | null;
}

export interface ImportRequestCounts {
  rows?: number;
  created?: number;
  updated?: number;
  failed?: number;
  columns?: string[];
  ignored_columns?: string[];
}

export interface ClientMe {
  id: string;
  email: string;
  name: string;
  must_reset_password: boolean;
  company: { slug: string; name: string; enabled_modules: string[] };
  role: RoleInfo;
}

export interface AdminMe {
  id: string;
  email: string;
  name: string;
  role: RoleInfo;
}

export interface QuickAction {
  key: string;
  label: string;
  module: string;
  required_level: number;
  target_route: string;
  /** Set by the server when the user has pinned this action (Phase 2). */
  pinned?: boolean;
}

/** One row of the "Customize quick actions" dialog: every action the user may
 *  take, with its current pin/hide state (includes hidden ones). */
export interface CustomizableQuickAction {
  key: string;
  label: string;
  module: string;
  pinned: boolean;
  hidden: boolean;
}

/** A contextual "next step" nudge on the dashboard (Phase 3): a data-state
 *  suggestion with a deep-link CTA. Dismissible per-user. */
export interface Suggestion {
  key: string;
  message: string;
  cta_label: string;
  target_route: string;
  priority: number;
}

export interface KpiSet {
  open_projects?: number;
  overdue_tasks?: number;
  open_deals?: number;
  low_stock_items?: number;
  unpaid_invoices_total?: number;
}

// --- Projects Analytics (docs/PROJECT_ANALYTICS_PLAN.md) ---------------------
// Role-tiered: the KPI row is always present; the chart blocks are present only
// when the caller has READ on `projects_analytics` (absent, never null).

export interface AnalyticsBudget {
  planned: number;
  actual: number;
  committed: number;
  variance: number;
  variance_pct: number | null;
}

export interface AnalyticsKpis {
  active: number;
  on_hold_blocked: number;
  overdue: number;
  open_exceptions: number;
  budget: AnalyticsBudget;
}

export interface StageCount { order: number; key: string; label: string; count: number }
export interface StageTime {
  order: number; key: string; label: string; avg_days: number; count: number;
}
export interface TopProject { code: string; name: string; planned: number; actual: number }
export interface CostByType { cost_type: string; amount: number }
export interface ExceptionRow {
  type: string; open: number; in_progress: number; total: number;
}
export interface ThroughputPoint { month: string; started: number; completed: number }

export interface ProjectAnalytics {
  kpis: AnalyticsKpis;
  by_stage?: StageCount[];
  time_in_stage?: StageTime[];
  budget?: {
    portfolio: { planned: number; actual: number; committed: number };
    top_projects: TopProject[];
    cost_by_type: CostByType[];
  };
  exceptions?: ExceptionRow[];
  throughput?: ThroughputPoint[];
}

export interface CalendarEvent {
  id: string;
  source_module: string;
  type: string;
  title: string;
  start: string;
  end: string | null;
  all_day: boolean;
  entity_ref: { module: string; type: string; id: string };
  color_key: string;
  /** Source detail for the quick view — keys vary by `type`, and the UI renders
   *  only the ones it recognises, so the server may add more freely. */
  meta?: Record<string, unknown>;
}

export interface ActivityEntry {
  id: string;
  actor_id: string;
  actor_name: string | null;
  action: string;
  module: string | null;
  entity: { type?: string; id?: string; label?: string };
  occurred_at: string;
}

/** A platform IP access rule (docs/IP_ACCESS_CONTROL_PLAN.md §2-A). */
export interface IpRule {
  id: string;
  kind: "allow" | "deny";
  match_type: "ip" | "cidr" | "country";
  value: string;
  reason: string | null;
  enabled: boolean;
  source: "seed" | "manual";
  family: number | null;
  created_at?: string;
  created_by?: string | null;
}

/** `POST /admin/ip-rules/test` verdict — "would this IP be allowed, by which rule?" */
export interface IpTestResult {
  ip: string;
  country: string | null;
  allowed: boolean;
  reason: string;
  matched_rule:
    | { id: string; kind: string; match_type: string; value: string }
    | null;
}

/** `GET /admin/ip-rules/whoami` — the IP the server sees for the current admin. */
export interface IpWhoami {
  ip: string;
  country: string | null;
}

export interface Company {
  id: string;
  name: string;
  slug: string;
  db_name?: string;
  status: string;
  seat_limit?: number;
  seats_used?: number;
  enabled_modules?: string[];
  provisioned_at?: string | null;
}

export interface PlatformDashboard {
  host: {
    cpu_pct: number;
    load_avg: number[];
    memory: { total: number; used: number; available: number; pct: number };
    disk: { total: number; used: number; free: number; pct: number };
    process: { pid: number; uptime_sec: number; workers: number };
  };
  rates: {
    requests_last_min: number;
    rate_limited_last_min: number;
    top_tenants: { tenant: string; requests: number; share_pct: number }[];
  };
  storage: {
    control: Record<string, number> | null;
    tenants: {
      tenant_id: string;
      slug?: string;
      data_size: number;
      storage_size: number;
      index_size: number;
      objects: number;
    }[];
    total_storage: number;
    trend: { captured_at: string; data_size: number }[];
  };
  activity: {
    companies_total: number;
    companies_active: number;
    companies_new_7d: number;
    active_users_24h_total: number;
    per_company: {
      company_id: string;
      name: string;
      slug: string;
      status: string;
      seats_used: number;
      seat_limit: number;
      last_activity_at: string | null;
      logins_24h: number;
      active_users_24h: number;
      module_usage: Record<string, number>;
    }[];
  };
}
