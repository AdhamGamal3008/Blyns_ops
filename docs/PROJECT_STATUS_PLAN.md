# Project Status Management — Plan

> **Cold-executable.** A future session can run this with no prior context.
> Feature branch: `project-status-management`. Module spec:
> `docs/modules/PROJECT_MANAGEMENT.md`. The machine is **9 stages** (v2.0) —
> `permissions.py:63 LAST_STAGE_ORDER = 9`.

---

## 1. The requirement

A project's status becomes **managed** rather than incidental. A user with the
right permission moves a project between:

| Status | How it is reached |
|---|---|
| **Active** | default on creation; resume from hold; restore from archive |
| **On hold** | manually paused, **or** parked by the engine on a severe gate failure |
| **Completed** | **only** by finishing stage 9 — never set by hand |
| **Archived** | manually, **from any status, at any stage, at any time** |

Rules, verbatim from the owner:

1. Archive is available **at all times**, not only at completion.
2. An archived project **moves to a separate tab** (out of the portfolio).
3. An archived project can be **recalled to any state other than completed**.

---

## 2. What exists today (verified, not assumed)

| Fact | Evidence |
|---|---|
| Status vocabulary already defined | `models.py:10` — `active/on_hold/completed/archived/cancelled` |
| `archived` + `cancelled` are never written by any code path | grep across `backend/app/modules/projects/` |
| Status is freely settable, no rules | `service.py:326 patch_project` — `status` is just another field on `ProjectPatch` |
| `completed` set at stage 9 only | `service.py:950` under `if order >= LAST_STAGE_ORDER` |
| `on_hold` is engine-owned | set `service.py:608`, `service.py:1134`; auto-cleared `service.py:1722 _maybe_clear_hold` |
| Portfolio list filters by status already | `service.py:167 list_projects(status=…)` |
| Analytics already treats archived as terminal | `analytics.py:31 _TERMINAL_STATUSES` |
| Dashboard "open projects" KPI counts `status == active` | `dashboard/repository.py:18` — archived already excluded, no change needed |
| Calendar does **not** exclude archived | `dashboard/repository.py calendar_projects` filters only `is_deleted` — **must fix** |
| UI already has a Tabs pattern | `ProjectsPage.tsx:172` Portfolio / Analytics |
| `_project()` is the single choke point for every project operation | `service.py:93` — the archive freeze hooks in here |

---

## 3. Design

### 3.1 One door for status

Today status rides on the generic PATCH with no validation. Replace that with a
single, guarded endpoint:

```
POST /api/v1/projects/{id}/status   { "status": "...", "reason": "..." }
```

and **remove `status` from `ProjectPatch`** so there is exactly one way in. This
mirrors the admin plane's `PATCH /admin/companies/{id}/status`.

### 3.2 Transition matrix

Rows are the current status, columns the requested one. `—` = rejected with
`INVALID_STATUS_TRANSITION` (409).

| from ↓ → to | active | on_hold | completed | archived |
|---|---|---|---|---|
| **active** | — | ✅ manual hold | ❌ never by hand (D1) | ✅ |
| **on_hold** | ✅ resume | — | ❌ | ✅ |
| **completed** | ✅ **re-open** (D2) | ❌ re-open first, then hold | — | ✅ |
| **archived** | ✅ restore | ✅ restore | ❌ **rule 3** | — |

Re-opening a completed project (`completed → active`) clears `completed_at`,
exactly like restoring from archive — a project must never be simultaneously
"active" and stamped complete.

Engine transitions are untouched and bypass this matrix: severe gate failure →
`on_hold`, stage 9 approval → `completed`.

### 3.3 Hold provenance — the sharp edge

`_maybe_clear_hold` flips **any** `on_hold` project back to `active` when the
last open report resolves. Introduce a manual hold and an unrelated report
resolution would silently un-pause a project a human deliberately paused.

Fix: record why the project is held.

```json
"hold": { "source": "manual" | "engine", "reason": "…", "by": "user…", "at": "…" }
```

`_maybe_clear_hold` clears **only** `source == "engine"`. A manual hold is
cleared only by an explicit resume. This is the single most important behaviour
in this change — it gets a dedicated test.

### 3.4 Archive freezes the machine

While `status == "archived"`, every mutating project operation is rejected with
`PROJECT_ARCHIVED` (409): stage submit/approve/reject, gate results, task runs,
document attach, deliverables, reports, job costs. Reads stay open, and the
status endpoint itself is exempt (otherwise a project could never be restored).

Enforced centrally in `_project()` (`service.py:93`) via a `mutating: bool`
argument, so a new endpoint cannot forget the guard.

### 3.5 Restore

Restoring asks for the target explicitly (`active` or `on_hold`) — never
`completed`, per rule 3. On restore, `completed_at` is cleared so a restored
project is not simultaneously "active" and stamped complete.

`status_history` (append-only) records every transition with actor, from, to,
reason and timestamp — the audit surface for "who archived this?".

### 3.6 Surfaces that must change

| Surface | Change |
|---|---|
| Portfolio list | default query excludes `archived` |
| **Archived tab** | `GET /projects?status=archived` — already supported by `list_projects` |
| Calendar | `calendar_projects` must exclude archived (and completed) milestones |
| Dashboard KPI | none — already counts `active` only |
| Analytics | none — `_TERMINAL_STATUSES` already excludes archived |

---

## 4. Decisions — LOCKED by owner 2026-07-16

**D1 — Can a user set `completed` by hand? → NO, machine-only.**
Completion is reached solely by stage-9 approval. A hand-set `completed` would
make the entire stage-gate system optional, and rule 3 already implies
completion is not something you pick.

**D2 — Can `completed` go back to `active` directly? → YES, direct re-open.**
(Owner chose this over archive-then-restore.) A finished project can be
re-opened for post-handover rework in one step. `completed_at` is cleared and
`status_history` records the re-open, so the trail survives. `completed →
on_hold` is deliberately **not** offered: re-open first, then hold.

**D3 — Which permission governs status changes? → `projects` WRITE.**
Reuses the existing resource; grants nothing new (status is already editable via
PATCH today) and needs no RBAC backfill migration.

---

## 5. Phases

Each phase ends with its tests green before the next begins.

### Phase 0 — branch + plan
`git checkout -b project-status-management`; commit this document.

### Phase 1 — backend status engine
| File | Change |
|---|---|
| `projects/models.py` | `ProjectStatusChange` payload; drop `status` from `ProjectPatch` |
| `projects/permissions.py` | `MANUAL_STATUSES`, `TRANSITIONS` matrix, `MUTATION_BLOCKED_STATUSES` |
| `projects/service.py` | `change_status()`; `hold` provenance; `_maybe_clear_hold` engine-only; `_project(mutating=True)` guard; clear `completed_at` on restore; `status_history` |
| `projects/router.py` | `POST /{id}/status` (`projects` WRITE) |
| `core/errors.py` | `INVALID_STATUS_TRANSITION`, `PROJECT_ARCHIVED` |

**Tests** (`tests/integration/test_projects_status.py`): full matrix table-driven;
manual hold survives report resolution; engine hold still auto-clears; archive
from every status incl. mid-stage; archived blocks stage submit/approve; restore
to active and to on_hold; restore to completed rejected; `completed_at` cleared;
`status_history` accumulates; RBAC (READ user gets 403).

### Phase 2 — surfaces
Portfolio excludes archived; calendar excludes archived/completed; activity log
entries `project.archived` / `project.restored` / `project.held` / `project.resumed`.
**Tests**: extend `test_client_dashboard.py` (archived milestones absent).

### Phase 3 — frontend
| File | Change |
|---|---|
| `projects/types.ts` | status types + transition map mirroring the backend |
| `projects/ProjectDetail.tsx` | status control beside the badge: Hold/Resume, Archive (always), Restore; reason prompt |
| `projects/ProjectsPage.tsx` | **Archived tab** (Portfolio / Archived / Analytics), Restore action, portfolio excludes archived |
| `projects/StatusControl.tsx` | new — the menu + confirm dialog |

**Tests** (`__tests__/ProjectStatus.test.tsx`): control offers exactly the legal
transitions per status; Completed never offered; Archive always offered; restore
dialog forbids completed.

### Phase 4 — proof
Sharded backend suite (4 shards — a single run OOM-kills the ephemeral mongod),
`ruff`, `mypy`, `tsc`, `vitest`, then a local browser pass on the real flows.
**Hand to owner for testing.** Merge → push → CI → Release tag → deploy per
`docs/DEVELOPMENT_TO_PRODUCTION.md`.

---

## 6. Prove it works

1. Create a project → status `active`; Archive at stage 1 → leaves Portfolio,
   appears under Archived.
2. Restore → choose **On hold** → back in Portfolio, badge `on hold`, Completed
   was never offered.
3. Manually hold a project that has an open report → resolve the report → it
   **stays** on hold (engine-hold regression guard).
4. Drive a project to stage 9 approval → `completed` without anyone setting it.
5. Archive the completed project → restore → lands `active`, `completed_at`
   cleared, `status_history` shows completed → archived → active.
6. Archived project rejects stage submit with `PROJECT_ARCHIVED`.

---

## 7. Traps — do not regress

- **`_maybe_clear_hold` must never clear a manual hold.** Without provenance,
  resolving any report un-pauses a deliberately paused project.
- **`completed` is machine-only.** Adding it to the manual matrix silently makes
  the entire stage-gate system optional.
- **The archive guard belongs in `_project()`**, not in each endpoint — a new
  endpoint added later must inherit it for free.
- **No migration needed**: `hold` / `status_history` / `completed_at` are
  additive and optional; absent means absent. Do **not** backfill.
- **`cancelled` stays in the vocabulary but out of the UI** — nothing writes it;
  removing it from the `Literal` would break `analytics.py:31` and any old row.
