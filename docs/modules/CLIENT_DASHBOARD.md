# MODULE: Client Dashboard

The tenant landing surface. Three regions: **Quick System Actions**, **Calendar
View**, **System Activity Panel**. RBAC resource: `dashboard` (plus `calendar`,
`activity`). Routes under `/api/v1/dashboard`, `/api/v1/calendar`,
`/api/v1/activity`. All tenant-bound.

---

## 1. Quick System Actions

Role-aware shortcuts to common cross-module operations. The server returns only
actions the user's role permits (WRITE on the target resource), so the UI renders
a filtered set.

`GET /api/v1/dashboard/quick-actions` → list of `{ key, label, module,
required_level, target_route }`. Examples:
- `project.new` (projects WRITE)
- `crm.lead.new` (crm WRITE)
- `inventory.adjust` (inventory WRITE)
- `finance.invoice.new` (finance WRITE)
- `employee.invite` (settings WRITE)

The action list is derived from enabled modules + the user's role map. Executing
an action just deep-links to the relevant module create flow; no business logic
lives here.

Also returns headline KPIs (respecting per-module READ permission):
`{ open_projects, overdue_tasks, open_deals, low_stock_items,
unpaid_invoices_total }`. Any KPI whose source module the user cannot READ is
omitted.

---

## 2. Calendar View

A unified calendar aggregating dated items **across every module the user can
READ**. This is a read/aggregation surface, not a separate event store (though
Settings may define standalone company events — see `SETTINGS.md`).

`GET /api/v1/calendar?from=&to=&modules=` → normalized events:
```json
{
  "id": "projects:task:665…",
  "source_module": "projects",
  "type": "task_due | milestone | deal_close | invoice_due | bill_due | company_event",
  "title": "Submit proposal",
  "start": "ISO-8601",
  "end": "ISO-8601 | null",
  "all_day": true,
  "entity_ref": { "module":"projects","type":"task","id":"…" },
  "color_key": "projects"
}
```

Aggregation sources:
- **projects** → task `due_date`, milestone dates.
- **crm** → deal `expected_close_date`, scheduled activities.
- **inventory** → reorder/expected-restock dates (if modeled).
- **finance** → invoice/bill due dates.
- **settings** → company calendar events (`calendar_events` collection).

Rules:
- Only include events from modules where the user's role is ≥ READ.
- Support month/week/day ranges via `from`/`to`; cap the window (e.g. 90 days).
- Clicking an event deep-links to its source entity.
- "View the whole system on a calendar" = the union above; users with lower
  permissions see a narrower union automatically.

---

## 3. System Activity Panel

A live feed of what's happening in the tenant, sourced from `activity_log`
(`ARCHITECTURE.md` §5).

`GET /api/v1/activity?module=&actor=&from=&to=&cursor=` → paginated feed:
```json
{
  "actor": { "id":"…", "name":"…" },
  "action": "project.created",
  "module": "projects",
  "entity": { "type":"project","id":"…","label":"Website Revamp" },
  "occurred_at": "ISO-8601"
}
```

Rules:
- Feed is filtered to modules the user can READ (a Viewer with `crm=NONE` never
  sees CRM activity).
- Filters: by module, actor, date range, action type.
- Real-time-ish via short polling (e.g. 15s) — no external pub/sub. Optionally a
  server-sent-events endpoint later, still custom.

---

## 4. API surface

```
GET /api/v1/dashboard/quick-actions
GET /api/v1/dashboard/kpis
GET /api/v1/calendar
GET /api/v1/activity
```

## 5. Seed (`modules/dashboard/seed.py`)
- Ensure `activity_log` indexes: `occurred_at` (desc), `module`, `actor_id`.
- Dashboard itself stores no primary data; it reads from other collections.

## 6. Acceptance criteria
- Quick actions shown to a user are exactly those their role can WRITE.
- Calendar merges dated items from all READ-permitted modules within the range
  and excludes modules the user cannot READ.
- Activity panel reflects a just-performed action within one poll cycle and
  respects module read permissions.
