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
  is_client_portal?: boolean; // scoped approval-only client-contact (PM §9)
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

export interface KpiSet {
  open_projects?: number;
  overdue_tasks?: number;
  open_deals?: number;
  low_stock_items?: number;
  unpaid_invoices_total?: number;
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
