# MODULE: CRM

RBAC resource: `crm`. Routes under `/api/v1/crm`. Tenant-bound.

---

## 1. Entities

### Account (company/customer)
```json
{ "_id":"…","name":"Globex","industry":"…","website":"…",
  "owner_id":"user…","address":{},"phone":"…",
  "status":"prospect|customer|inactive","tags":["…"],
  "created_at":"…","updated_at":"…","created_by":"…","is_deleted":false }
```

### Contact (person, optionally linked to an account)
```json
{ "_id":"…","account_id":"… | null","first_name":"…","last_name":"…",
  "email":"…","phone":"…","title":"…","owner_id":"…","tags":["…"] }
```

### Lead (unqualified)
```json
{ "_id":"…","name":"…","email":"…","phone":"…","source":"…",
  "status":"new|contacted|qualified|unqualified|converted",
  "owner_id":"…","converted_to":{"account_id":null,"contact_id":null,"deal_id":null} }
```

### Deal / Opportunity
```json
{ "_id":"…","title":"…","account_id":"…","contact_id":"…",
  "pipeline":"default","stage":"new|qualified|proposal|negotiation|won|lost",
  "amount":0,"currency":"USD","probability_pct":0,
  "expected_close_date":"…","owner_id":"…","lost_reason":null,
  "created_at":"…","updated_at":"…","created_by":"…","is_deleted":false }
```

### Activity (call/meeting/note/task on any CRM entity)
```json
{ "_id":"…","entity_ref":{"type":"account|contact|lead|deal","id":"…"},
  "type":"call|email|meeting|note|task","subject":"…","body":"…",
  "due_at":"… | null","done":false,"owner_id":"…","created_at":"…" }
```

---

## 2. Behavior

- **Pipeline:** deals move through ordered `stage`s; store stage-change history in
  activity/audit. `won`/`lost` are terminal; `lost` requires `lost_reason`.
- **Lead conversion:** converting a lead creates/links account + contact + deal
  atomically and stamps `converted_to`.
- **Ownership:** every record has an `owner_id`; list views support "mine vs all"
  filters. (Row-level restriction by owner is optional and configured in
  Settings; default is tenant-wide visibility for READ users.)
- **KPIs:** open deals count + pipeline value feed dashboard.
- Scheduled `activity.due_at` and deal `expected_close_date` feed the calendar.
- All mutations write `activity_log` (`crm.deal.stage_changed`, etc.).

---

## 3. API surface

```
GET/POST/PATCH/DELETE   /api/v1/crm/accounts[/{id}]
GET/POST/PATCH/DELETE   /api/v1/crm/contacts[/{id}]
GET/POST/PATCH/DELETE   /api/v1/crm/leads[/{id}]
POST                    /api/v1/crm/leads/{id}/convert
GET/POST/PATCH/DELETE   /api/v1/crm/deals[/{id}]
PATCH                   /api/v1/crm/deals/{id}/stage
GET/POST/PATCH/DELETE   /api/v1/crm/activities[/{id}]
GET                     /api/v1/crm/pipeline          # deals grouped by stage w/ totals
```
Guarded: READ for GET, WRITE for mutations.

## 4. Seed (`modules/crm/seed.py`)
Indexes: `accounts.status`, `contacts.account_id`, `contacts.email`,
`leads.status`, `deals (stage, expected_close_date)`, `deals.account_id`,
`activities.entity_ref.id`, `activities.due_at`.
Default: one `default` pipeline definition doc with ordered stages.

## 5. Calendar contribution
`deal_close` (expected_close_date), CRM `activity` (due_at).

## 6. Acceptance criteria
- Converting a lead produces linked account/contact/deal and marks the lead
  converted.
- Moving a deal to `lost` without a reason is rejected.
- Pipeline endpoint returns stage buckets with counts and summed amounts.
- `crm=NONE` users get `PERMISSION_DENIED` on all CRM routes and see no CRM
  activity/calendar entries.
