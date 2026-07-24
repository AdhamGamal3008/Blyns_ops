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
  "color_key": "projects",
  "meta": { "code":"PRJ-0009", "status":"active", "stage_order": 7 }
}
```

`meta` carries the handful of source fields the quick view (§2.1) shows without
navigating away. Its keys vary by `type` and the UI renders only the ones it
recognises, so the server may add more without breaking an older client. It is
filled from documents the aggregation already reads — **enriching it must never
cost an extra query per event**. By type:

| `type` | `meta` |
|---|---|
| projects (all) | `project`, `code`, `status`, `stage_order`, plus `milestone` / `stage` / `gate` |
| `deal_close` | `amount`, `currency`, `stage`, `probability_pct` |
| `task_due` (crm) | `activity_type`, `notes`, `about` |
| `invoice_due` / `bill_due` | `counterparty`, `total`, `paid`, `balance`, `currency`, `status` |
| `company_event` | `visibility` |

`meta` is not a permission bypass: an event is only emitted at all when the user
can READ its module, so a user without finance never receives an invoice event
or its amounts.

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

**Which cell an event sits in.** An `all_day` event is a calendar *date*, stored
at UTC midnight, and must be read back in UTC — taking its local date shows it a
day early to every viewer west of Greenwich. A timed event is a *moment*, and
belongs on the day it falls on in the viewer's own timezone. Using one rule for
both puts a late-evening deadline in tomorrow's cell.

### 2.1 Quick view

Every entry on the calendar opens a detail popover — title, type, module, when,
the `meta` rows for its type, and an "Open in …" link to the source entity.

It opens **two ways, and both are required**: hovering previews it (what a
pointer reaches for), and clicking or pressing Enter pins it open. Hover alone
is unreachable by keyboard and touch, so it can never be the only path. A
*pinned* panel survives the pointer leaving — otherwise moving the mouse toward
its own link would dismiss it — and takes focus, so a keyboard user lands inside
it. Escape or an outside click closes it.

A day cell shows the first three entries; **+N more** opens the day's full list,
each row deep-linking on its own.

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
- Every calendar entry is a focusable control that opens its detail on hover
  **and** on click/Enter; a hovered panel closes on leave, a pinned one does not.
- A calendar detail deep-links to its source entity, and `+N more` opens the
  day's full list.
- Every event carries a `meta`, populated without an extra query per event, and
  a user who cannot READ a module receives neither its events nor their detail.
- Activity panel reflects a just-performed action within one poll cycle and
  respects module read permissions.
