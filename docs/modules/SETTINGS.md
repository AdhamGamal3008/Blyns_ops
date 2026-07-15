# MODULE: Settings

RBAC resource: `settings`. Routes under `/api/v1/settings`. Tenant-bound.
The client-side control panel: company profile, employees, client roles,
calendar events, security, and module visibility.

---

## 1. Sections

### 1.1 Company profile
```json
{ "_id":"company_profile","name":"…","legal_name":"…","logo_ref":"…",
  "timezone":"…","currency":"USD","fiscal_year_start":"01-01",
  "contact":{"email":"…","phone":"…","address":{}} }
```
`GET/PATCH /api/v1/settings/company`. Timezone/currency affect calendar +
finance display.

### 1.2 Employees (client-managed, within seat limit)
- `GET /api/v1/settings/employees`
- `POST /api/v1/settings/employees` — create (checks seat limit via control
  plane; increments `seats_used`).
- `PATCH /api/v1/settings/employees/{id}` — edit name/role.
- `POST /api/v1/settings/employees/{id}/reset-password` — client-side reset
  (sets temp password + `must_reset_password`).
- `PATCH /api/v1/settings/employees/{id}/block` — client Owner may block their
  own employees (cannot override a platform-level company block).
- `POST /api/v1/settings/employees/{id}/unlock` — clear failed-login lockout.

All require `settings` WRITE (and, for security actions, are also gated by the
`security_policy` concept from `AUTH_RBAC.md`).

### 1.3 Client roles (RBAC editor)
Manage tenant roles as `{ name, permissions: { resource: Level } }` over the
client resources (`dashboard, calendar, activity, projects, crm, inventory,
finance, settings`).
- `GET/POST/PATCH/DELETE /api/v1/settings/roles[/{id}]`.
- Guards: cannot delete a role still assigned to users; cannot delete the last
  Owner-equivalent; `settings` WRITE required.
- Editing a role re-evaluates permissions for holders on next request (no stale
  cache).

### 1.4 Calendar events (standalone company events)
The one place the calendar has its **own** stored events (holidays, all-hands,
custom reminders) in addition to aggregated module dates.
```json
{ "_id":"…","title":"…","start":"…","end":"…","all_day":true,
  "visibility":"company|role|owner","created_by":"…" }
```
- `GET/POST/PATCH/DELETE /api/v1/settings/calendar-events[/{id}]`.
- These surface in the Dashboard calendar as `company_event`.

### 1.5 Security policy (client view)
- Read the company failed-login threshold/lockout (set by platform admin; client
  may view, and may request changes if permitted). Whether clients can edit their
  own threshold is a platform decision — expose as read-only unless the company
  is granted `security_policy` WRITE.

### 1.6 Module visibility
Reflects `companies.enabled_modules` (set by platform admin). Clients see which
modules are enabled; toggling on the client side is allowed only for modules the
platform permits self-service, and enabling runs that module's `seed()`.

---

## 2. API surface (summary)
```
GET/PATCH               /api/v1/settings/company
GET/POST/PATCH          /api/v1/settings/employees[/{id}]
POST                    /api/v1/settings/employees/{id}/reset-password
POST                    /api/v1/settings/employees/{id}/unlock
PATCH                   /api/v1/settings/employees/{id}/block
GET/POST/PATCH/DELETE   /api/v1/settings/roles[/{id}]
GET/POST/PATCH/DELETE   /api/v1/settings/calendar-events[/{id}]
GET                     /api/v1/settings/security
GET                     /api/v1/settings/modules
```

## 3. Seed (`modules/settings/seed.py`)
- Create `company_profile` doc from onboarding payload.
- Create default client roles (Owner/Manager/Member/Viewer) — this is where the
  provisioning `seed_rbac` step is implemented.
- Indexes: `roles.name` (unique), `calendar_events.start`.

## 4. Acceptance criteria
- Creating an employee is blocked once seat limit is reached.
- Editing a client role immediately changes what holders can access.
- Company calendar events appear in the Dashboard calendar respecting
  visibility.
- A client Owner can block/unlock their own employees but cannot lift a
  platform-imposed company block.
