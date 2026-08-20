"""Project Management orchestration (docs/modules/PROJECT_MANAGEMENT.md).

PM owns the state machine and delegates domain data to the other modules (§1):
CRM holds the account, Inventory holds the stock, Finance holds the money. The
integration points call those modules' services rather than touching their
collections, so their own guards (INSUFFICIENT_STOCK, balanced entries) apply
exactly as they do anywhere else.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

from app.core import storage
from app.core.audit import write_activity
from app.core.config import settings
from app.core.errors import (
    INVALID_STATUS_TRANSITION,
    PERMISSION_DENIED,
    PROJECT_ARCHIVED,
    TENANT_NOT_FOUND,
    VALIDATION_ERROR,
    DomainError,
)
from app.modules.projects import engines
from app.modules.projects import repository as repo
from app.modules.projects.models import (
    ChecklistMark,
    ClientAcceptanceCreate,
    DelegationCreate,
    DeliverableCreate,
    DocumentSupply,
    GateConfigPatch,
    GateDocumentAttach,
    GateResultCreate,
    GateWaive,
    JobCostCreate,
    ProjectCreate,
    ProjectPatch,
    ProjectStatusChange,
    ReportCreate,
    ReportPatch,
    RevisionCreate,
    StageConfigPatch,
)
from app.modules.projects.permissions import (
    COMPLETION_FIELDS,
    DEFAULT_GATE_DOCUMENT_KIND,
    DEFAULT_REJECT_REPORT,
    FIRST_STAGE_ORDER,
    FROZEN_STATUSES,
    GATE_DOCUMENT_KINDS,
    LAST_STAGE_ORDER,
    OPEN_REPORT_STATUSES,
    STATUS_TRANSITIONS,
)
from app.tenant.deps import ClientPrincipal


def _now() -> datetime:
    return datetime.now(UTC)


async def _log(
    principal: ClientPrincipal, action: str, entity: dict,
    details: dict | None = None,
) -> None:
    await write_activity(
        principal.tenant_db,
        actor_id=str(principal.user["_id"]),
        action=action,
        entity=entity,
        details=details or {},
        actor_name=principal.user["name"],
        module="projects",
    )


def _oid(value: str, what: str) -> ObjectId:
    try:
        return ObjectId(value)
    except Exception as exc:
        raise DomainError(TENANT_NOT_FOUND, f"{what} not found.", 404) from exc


async def _require(
    principal: ClientPrincipal, coll: str, oid: ObjectId, what: str
) -> dict:
    doc = await repo.get(principal.tenant_db, coll, oid)
    if doc is None:
        raise DomainError(TENANT_NOT_FOUND, f"{what} not found.", 404)
    return doc


async def _project(
    principal: ClientPrincipal, project_id: str, *, mutating: bool = True
) -> dict:
    """Load a project, refusing to mutate a frozen (archived) one.

    `mutating` defaults to True so the guard is inherited by default: a new
    endpoint that forgets to think about archiving is safe, and only the read
    paths opt out. Reads stay open on an archived project — you must be able to
    look at what you parked (docs/PROJECT_STATUS_PLAN.md §3.4).
    """
    project = await _require(
        principal, repo.PROJECTS, _oid(project_id, "Project"), "Project"
    )
    if mutating and project.get("status") in FROZEN_STATUSES:
        raise DomainError(
            PROJECT_ARCHIVED,
            "This project is archived. Restore it before making changes.",
            http_status=409,
            details={"status": project["status"], "code": project.get("code")},
        )
    return project


async def _definition_in(db: Any, scope: repo.ConfigScope, order: int) -> dict:
    definition = await repo.stage_def_by_order(db, order, scope)
    if definition is not None:
        return definition
    # A missing stage and a missing CONFIGURATION are different failures: the
    # second means this workspace was never migrated (or a version was pruned out
    # from under a live project), and telling the caller "stage 1 is not defined"
    # sends them looking in the wrong place (G-1).
    if not await repo.stage_defs(db, scope):
        raise DomainError(
            VALIDATION_ERROR,
            f"The '{scope.workflow_type}' workflow is not seeded on this "
            "workspace — re-seed the Projects module "
            "(scripts/migrate_projects_v4.py) before working on this project.",
            409,
        )
    raise DomainError(TENANT_NOT_FOUND, f"Stage {order} is not defined.", 404)


async def _definition(principal: ClientPrincipal, project: dict, order: int) -> dict:
    """The stage definition a PROJECT runs at `order`.

    Read from the configuration VERSION the project pinned at creation, never the
    tenant's current default: two configurations can define the same stage with
    different documents, gates and thresholds, and a published version must not
    move a running project (D1/G-5).
    """
    db = principal.tenant_db
    return await _definition_in(db, await repo.scope_for_project(db, project), order)


async def _resolve_configuration(db: Any, payload: ProjectCreate) -> dict | None:
    """Which project configuration a new project runs against (Stage 1).

    Resolution order:
      1. an explicit `configuration_id` — what the Stage-1 picker sends;
      2. `workflow_type: "concurrent"` — back-compat for callers that predate
         configurations, mapped onto the Concurrent system config;
      3. the tenant's **default** configuration, which is what "I didn't choose"
         means once a tenant has built its own (G-4).

    Returns None on a tenant the v4 migration has not reached — that project
    carries no pin and resolves through the legacy workflow_type template, which
    still works (docs/PROJECT_CONFIGURATIONS_PLAN.md G-1).
    """
    if payload.configuration_id:
        config = await repo.project_config(
            db, _oid(payload.configuration_id, "Project configuration")
        )
        if config is None:
            raise DomainError(
                TENANT_NOT_FOUND, "Project configuration not found.", 404
            )
        if config.get("is_active") is False:
            raise DomainError(
                VALIDATION_ERROR,
                f"The '{config['name']}' configuration is deactivated and cannot "
                "be used for new projects.",
                422,
            )
        return config
    if payload.workflow_type != "sequential":
        return await repo.system_config(db, payload.workflow_type)
    return await repo.default_project_config(db)


# --- projects & portfolio (§12) ----------------------------------------------

async def list_projects(
    principal: ClientPrincipal, status: str | None, pm_id: str | None,
    stage: int | None, skip: int, limit: int,
) -> tuple[list[dict], int]:
    query: dict[str, Any] = {}
    if status:
        query["status"] = status
    else:
        # Rule 2: archived projects live in their own tab. An unfiltered
        # portfolio is the working list, so it excludes them; the tab asks for
        # them explicitly with ?status=archived.
        query["status"] = {"$ne": "archived"}
    if pm_id:
        query["pm_id"] = pm_id
    if stage:
        query["current_stage_order"] = stage
    return await repo.list_docs(
        principal.tenant_db, repo.PROJECTS, query, skip, limit,
        sort=[("current_stage_order", 1), ("created_at", -1)],
    )


async def get_project(principal: ClientPrincipal, project_id: str) -> dict:
    return await _project(principal, project_id, mutating=False)


async def create_project(principal: ClientPrincipal, payload: ProjectCreate) -> dict:
    """Stage 1 (§7): create the record and enter the machine at stage 1.

    §1: the client record itself belongs to CRM — we link, never copy it.
    """
    db = principal.tenant_db

    configuration = await _resolve_configuration(db, payload)
    workflow_type = (
        configuration["workflow_shape"] if configuration else payload.workflow_type
    )

    # The chosen configuration must actually have its stages seeded on this tenant,
    # or the project would be stranded at Stage 1 with nothing to unlock. A tenant
    # the v4 migration has not reached has no configurations at all and falls back
    # to the legacy workflow_type template (G-1).
    scope = (
        repo.scope_of(configuration) if configuration
        else repo.ConfigScope(workflow_type=workflow_type)
    )
    if not await repo.stage_defs(db, scope):
        label = configuration["name"] if configuration else workflow_type
        raise DomainError(
            VALIDATION_ERROR,
            f"The '{label}' workflow is not available on this "
            "workspace yet — the Projects module must be re-seeded "
            "(scripts/migrate_projects_v4.py) before projects can be created "
            "against it.",
            422,
        )

    crm_account_id: ObjectId | None = None
    if payload.crm_account_id:
        from app.modules.crm import repository as crm_repo

        account = await crm_repo.get(
            db, crm_repo.ACCOUNTS, _oid(payload.crm_account_id, "Account")
        )
        if account is None:
            raise DomainError(TENANT_NOT_FOUND, "CRM account not found.", 404)
        crm_account_id = account["_id"]

    first = await _definition_in(db, scope, FIRST_STAGE_ORDER)
    code = await repo.next_code(db)
    doc = await repo.insert(db, repo.PROJECTS, {
        "code": code,
        "name": payload.name,
        "scope": payload.scope,
        "workflow_type": workflow_type,
        # Pin the configuration VERSION current right now: publishing a new version
        # later must not move this project's stages or gates (D1/G-5).
        "configuration_id": configuration["_id"] if configuration else None,
        "config_version": (
            int(configuration["current_version"]) if configuration else None
        ),
        "crm_account_id": crm_account_id,
        "current_stage_order": first["order"],
        "current_stage_key": first["key"],
        "status": "active",
        "pm_id": payload.pm_id or str(principal.user["_id"]),
        "team_ids": payload.team_ids,
        "milestone_schedule": [m.model_dump() for m in payload.milestone_schedule],
        "schedule": payload.schedule.model_dump() if payload.schedule else {},
        "budget": {
            "planned": payload.planned_budget, "committed": 0.0,
            "actual": 0.0, "currency": payload.currency,
        },
        "stage_history": [],
        "created_by": str(principal.user["_id"]),
    })

    instance = await _enter_stage(principal, doc, first)
    await _log(principal, "project.created",
               {"type": "project", "id": str(doc["_id"]), "label": doc["name"]},
               {"code": code, "stage": first["key"]})
    doc["stage_instance"] = instance
    return doc


async def _enter_stage(
    principal: ClientPrincipal, project: dict, definition: dict
) -> dict:
    """Create (or find) the stage instance and let the decision engine place it."""
    db = principal.tenant_db
    instance = await repo.upsert_stage_instance(db, project["_id"], definition["order"], {
        "project_id": project["_id"],
        "stage_order": definition["order"],
        "stage_key": definition["key"],
        "status": "pending",
        "entered_at": _now(),
        "gate_results": [],
        "task_results": [],
        "documents_supplied": [],
        "checklist_done": [],
        "approval_id": None,
        "recovery_loops": 0,
        "blocking_reason": None,
        "created_at": _now(),
        "updated_at": _now(),
    })
    result = await engines.run_decision_engine(db, project, definition, instance)
    await _log(principal, "stage.entered",
               {"type": "project", "id": str(project["_id"]), "label": project["name"]},
               {"stage": definition["key"], "order": definition["order"],
                "status": result["instance"]["status"]})
    return result["instance"]


async def _enter_unlocked_stages(
    principal: ClientPrincipal, project: dict
) -> list[tuple[dict, dict]]:
    """Enter every stage whose declared dependencies are all approved and which has
    not been entered yet. A sequential project opens exactly the next stage; a
    concurrent one can open several at once (docs/CONCURRENT_WORKFLOW_PLAN.md).
    Returns the (definition, instance) pairs newly entered, lowest order first."""
    db = principal.tenant_db
    defs = await repo.stage_defs(db, await repo.scope_for_project(db, project))
    instances = {
        i["stage_order"]: i for i in await repo.stage_instances(db, project["_id"])
    }
    approved = {
        d["key"] for d in defs
        if (inst := instances.get(int(d["order"]))) and inst.get("status") == "approved"
    }
    newly: list[tuple[dict, dict]] = []
    for definition in sorted(defs, key=lambda d: int(d["order"])):
        if int(definition["order"]) in instances:
            continue  # already entered
        deps = [
            g["depends_on"] for g in (definition.get("entry_gates") or [])
            if g.get("type") == "dependency"
        ]
        if all(dep in approved for dep in deps):
            instance = await _enter_stage(principal, project, definition)
            newly.append((definition, instance))
    return newly


async def patch_project(
    principal: ClientPrincipal, project_id: str, patch: ProjectPatch
) -> dict:
    project = await _project(principal, project_id)
    fields = {k: v for k, v in patch.model_dump(exclude_unset=True).items() if v is not None}
    if "milestone_schedule" in fields:
        fields["milestone_schedule"] = [
            m.model_dump() if hasattr(m, "model_dump") else m
            for m in (patch.milestone_schedule or [])
        ]
    if "planned_budget" in fields:
        budget = dict(project.get("budget") or {})
        budget["planned"] = fields.pop("planned_budget")
        fields["budget"] = budget
    if "crm_account_id" in fields:
        fields["crm_account_id"] = _oid(fields["crm_account_id"], "Account")
    if not fields:
        return project
    fields["updated_by"] = str(principal.user["_id"])
    updated = await repo.update(
        principal.tenant_db, repo.PROJECTS, project["_id"], fields
    )
    assert updated is not None
    await _log(principal, "project.updated",
               {"type": "project", "id": project_id, "label": updated["name"]},
               {"fields": [k for k in fields if k != "updated_by"]})
    return updated


async def change_status(
    principal: ClientPrincipal, project_id: str, payload: ProjectStatusChange
) -> dict:
    """The one door for a managed status change (docs/PROJECT_STATUS_PLAN.md).

    `mutating=False` because this endpoint is precisely how an archived project
    gets un-frozen — guarding it would make archiving a one-way trip.
    """
    project = await _project(principal, project_id, mutating=False)
    current = project.get("status") or "active"
    target = payload.status

    same = target == current
    # Re-holding a project the ENGINE parked is a real request, not a no-op: it
    # converts the hold to a manual one, so resolving the recovery report no
    # longer releases a project a human wants kept parked (§3.3).
    upgrade_hold = (
        same and target == "on_hold"
        and (project.get("hold") or {}).get("source") != "manual"
    )
    if same and not upgrade_hold:
        return project

    if not same:
        allowed = STATUS_TRANSITIONS.get(current, ())
        if target not in allowed:
            raise DomainError(
                INVALID_STATUS_TRANSITION,
                f"A {current.replace('_', ' ')} project cannot be moved to "
                f"{target.replace('_', ' ')}.",
                http_status=409,
                details={"from": current, "to": target, "allowed": list(allowed)},
            )

    now = _now()
    actor = str(principal.user["_id"])
    fields: dict[str, Any] = {"status": target, "updated_by": actor}

    if target == "on_hold":
        # Provenance is what stops _maybe_clear_hold from silently resuming a
        # project a human deliberately paused (§3.3).
        fields["hold"] = {
            "source": "manual", "reason": payload.reason,
            "by": actor, "at": now,
        }
    elif current == "on_hold":
        fields["hold"] = None  # resumed or archived out of a hold

    # Leaving `completed` (re-open, or restore from an archived-completed) must
    # clear the completion stamp — nothing is both active and complete.
    if current == "completed" or (current == "archived" and project.get("completed_at")):
        for field in COMPLETION_FIELDS:
            fields[field] = None

    history = list(project.get("status_history") or [])
    history.append({
        "from": current, "to": target, "reason": payload.reason,
        "by": actor, "by_name": principal.user.get("name"), "at": now,
    })
    fields["status_history"] = history

    updated = await repo.update(
        principal.tenant_db, repo.PROJECTS, project["_id"], fields
    )
    assert updated is not None

    # Name the event by the most meaningful half of the move. Leaving the
    # archive is a "restore" whichever state it lands in — that is the fact a
    # reader of the feed cares about, more than the landing state.
    if target == "archived":
        action = "project.archived"
    elif current == "archived":
        action = "project.restored"
    elif current == "completed":
        action = "project.reopened"
    elif target == "on_hold":
        action = "project.held"
    else:
        action = "project.resumed"
    await _log(principal, action,
               {"type": "project", "id": project_id, "label": updated["name"]},
               {"code": updated.get("code"), "from": current, "to": target,
                "reason": payload.reason})
    return updated


async def delete_project(principal: ClientPrincipal, project_id: str) -> None:
    project = await _project(principal, project_id, mutating=False)
    await repo.soft_delete(
        principal.tenant_db, repo.PROJECTS, project["_id"], str(principal.user["_id"])
    )
    await _log(principal, "project.deleted",
               {"type": "project", "id": project_id, "label": project["name"]})


async def timeline(principal: ClientPrincipal, project_id: str) -> dict:
    """§12 — stages + milestones for the Gantt view."""
    project = await _project(principal, project_id, mutating=False)
    db = principal.tenant_db
    scope = await repo.scope_for_project(db, project)
    definitions = await repo.stage_defs(db, scope)
    instances = {
        i["stage_order"]: i for i in await repo.stage_instances(db, project["_id"])
    }
    # The detail header names the configuration this project is pinned to; resolving
    # it here saves the client a second round-trip just to turn an id into a label.
    configuration = (
        await repo.project_config(db, scope.configuration_id)
        if scope.configuration_id is not None else None
    )
    return {
        "project_id": project_id,
        # tolerate legacy/partial docs that predate the stage machine
        "code": project.get("code"),
        # the shape drives the pipeline view; the pin tells the UI which
        # configuration version it is actually looking at
        "workflow_type": project.get("workflow_type", "sequential"),
        "configuration_id": scope.configuration_id,
        "config_version": scope.config_version,
        "configuration_name": configuration["name"] if configuration else None,
        "current_stage_order": project.get("current_stage_order"),
        "milestones": project.get("milestone_schedule") or [],
        "stages": [
            {
                "order": d["order"],
                "key": d["key"],
                "name": d["name"],
                "approver_role": d.get("approver_role"),
                "status": (instances.get(d["order"]) or {}).get("status", "pending"),
                "entered_at": (instances.get(d["order"]) or {}).get("entered_at"),
                "recovery_loops": (instances.get(d["order"]) or {}).get("recovery_loops", 0),
                "blocking_reason": (instances.get(d["order"]) or {}).get("blocking_reason"),
            }
            for d in definitions
        ],
    }


async def board(principal: ClientPrincipal, project_id: str) -> dict:
    """§12 — the current stage's tasks/gates for the Kanban view."""
    project = await _project(principal, project_id, mutating=False)
    if not project.get("current_stage_order"):
        # a legacy/partial doc never entered the machine — nothing to board
        return {"project_id": project_id, "stage": None, "tasks": [],
                "waiting_on": [], "blocked_by": [], "blocking_reason": None,
                "open_reports": []}
    order = int(project["current_stage_order"])
    definition = await _definition(principal, project, order)
    instance = await repo.stage_instance(principal.tenant_db, project["_id"], order)
    if instance is None:
        instance = await _enter_stage(principal, project, definition)
    return {
        "project_id": project_id,
        "stage": {"order": order, "key": definition["key"], "name": definition["name"],
                  "status": instance["status"]},
        "tasks": instance.get("task_results") or [],
        "waiting_on": instance.get("waiting_on") or [],
        "blocked_by": instance.get("blocked_by") or [],
        "blocking_reason": instance.get("blocking_reason"),
        "open_reports": [
            {"id": str(r["_id"]), "type": r["type"], "title": r["title"],
             "status": r["status"]}
            for r in await repo.open_reports(
                principal.tenant_db, project["_id"], OPEN_REPORT_STATUSES
            )
        ],
    }


# --- stage machine (§12) -----------------------------------------------------

async def list_stages(principal: ClientPrincipal, project_id: str) -> list[dict]:
    return (await timeline(principal, project_id))["stages"]


async def get_stage(principal: ClientPrincipal, project_id: str, order: int) -> dict:
    project = await _project(principal, project_id, mutating=False)
    definition = await _definition(principal, project, order)
    db = principal.tenant_db
    instance = await repo.stage_instance(db, project["_id"], order)
    if instance is None:
        raise DomainError(
            TENANT_NOT_FOUND, f"Project has not reached stage {order}.", 404
        )
    evaluation = await engines.evaluate_stage(db, project, definition, instance)
    approval = await repo.open_approval(db, instance["_id"])
    return {
        "definition": definition,
        "instance": instance,
        "evaluation": evaluation,
        "approval": approval,
        "gate_results": await repo.gate_results_for(db, instance["_id"]),
    }


async def supply_document(
    principal: ClientPrincipal, project_id: str, order: int,
    gate_key: str, payload: DocumentSupply,
) -> dict:
    """§4: waiting → in_progress once the missing document is supplied. The
    submission may optionally reference a project document (deliverable) as its
    evidence — recorded on the stage with who attached it and when."""
    project = await _project(principal, project_id)
    definition = await _definition(principal, project, order)
    db = principal.tenant_db
    instance = await repo.stage_instance(db, project["_id"], order)
    if instance is None:
        raise DomainError(TENANT_NOT_FOUND, f"Stage {order} not reached.", 404)

    gate = next(
        (g for g in (definition.get("entry_gates") or []) if g.get("key") == gate_key),
        None,
    )
    if gate is None:
        raise DomainError(
            VALIDATION_ERROR,
            f"Stage {order} has no entry gate '{gate_key}'.", 422,
        )
    # A document gate is only satisfied by evidence — a file or a URL. Phase
    # gates (a dependency on a foundational phase, e.g. acclimation_complete)
    # have no document to show, so those are still marked directly.
    if gate.get("type") == "document" and not payload.deliverable_id:
        raise DomainError(
            VALIDATION_ERROR,
            f"'{gate_key}' requires a document — attach a file or a URL.", 422,
        )

    fields: dict[str, Any] = {}
    if payload.deliverable_id:
        deliverable = await db[repo.DELIVERABLES].find_one({
            "_id": _oid(payload.deliverable_id, "Deliverable"),
            "project_id": project["_id"], "is_deleted": {"$ne": True},
        })
        if deliverable is None:
            raise DomainError(TENANT_NOT_FOUND, "Referenced document not found.", 404)
        # one reference per gate: drop any prior one, then record this submission.
        # source_type/file_ref are denormalized so an approver can open the
        # evidence straight from the stage, without listing project documents.
        latest = (deliverable.get("versions") or [{}])[-1]
        refs = [r for r in (instance.get("document_refs") or [])
                if r.get("gate_key") != gate_key]
        refs.append({
            "gate_key": gate_key,
            "deliverable_id": str(deliverable["_id"]),
            "title": deliverable["title"],
            "version": deliverable.get("current_version", 1),
            "source_type": latest.get("source_type", "url"),
            "file_ref": latest.get("file_ref"),
            "by": str(principal.user["_id"]),
            "at": _now(),
        })
        fields["document_refs"] = refs

    supplied = set(instance.get("documents_supplied") or [])
    supplied.add(gate_key)
    fields["documents_supplied"] = sorted(supplied)
    await repo.set_stage_fields(db, instance["_id"], fields)
    instance = await repo.stage_instance(db, project["_id"], order)
    assert instance is not None
    result = await engines.run_decision_engine(db, project, definition, instance)
    await _log(principal, "gate.passed",
               {"type": "project", "id": project_id, "label": project["name"]},
               {"stage": definition["key"], "gate": gate_key, "type": "document"})
    return result["instance"]


async def record_gate_result(
    principal: ClientPrincipal, project_id: str, order: int,
    gate_key: str, payload: GateResultCreate,
) -> dict:
    """§3.5/§8 — log a physical measurement or inspection and score it.

    The caller supplies readings; the engine decides pass/fail against the
    tenant's seeded threshold. A caller never declares `passed` itself.
    """
    project = await _project(principal, project_id)
    definition = await _definition(principal, project, order)
    db = principal.tenant_db
    instance = await repo.stage_instance(db, project["_id"], order)
    if instance is None:
        raise DomainError(TENANT_NOT_FOUND, f"Stage {order} not reached.", 404)

    # The threshold is the one THIS project pinned — another configuration may
    # define the same gate with a different tolerance (G-3, G-5).
    rule = await repo.gate_rule(db, gate_key, await repo.scope_for_project(db, project))
    if rule is None:
        raise DomainError(TENANT_NOT_FOUND, f"Gate '{gate_key}' is not defined.", 404)
    attach = rule.get("attach_to_stages") or []
    if attach and definition["key"] not in attach:
        raise DomainError(
            VALIDATION_ERROR,
            f"Gate '{gate_key}' does not attach to stage '{definition['key']}'.",
            http_status=422,
        )

    passed, severe, explanation = engines.evaluate_gate_result(rule, payload.model_dump())
    result = await repo.insert(db, repo.GATE_RESULTS, {
        "stage_instance_id": instance["_id"],
        "project_id": project["_id"],
        "gate_key": gate_key,
        "type": rule.get("type"),
        "captured_by": str(principal.user["_id"]),
        "captured_at": _now(),
        "readings": payload.readings,
        "checklist_results": payload.checklist_results,
        "threshold": rule.get("threshold"),
        "passed": passed,
        "severe": severe,
        "explanation": explanation,
        "notes": payload.notes,
    })

    instance = await repo.stage_instance(db, project["_id"], order)
    assert instance is not None
    engine_result = await engines.run_decision_engine(db, project, definition, instance)

    rolled_to: str | None = None
    if severe:
        recovery = definition.get("recovery") or {}
        report_type = (
            (rule.get("severe_threshold") or {}).get("report_type")
            or recovery.get("report_type")
            or ("change" if recovery.get("action") == "return_to_stage" else "issue")
        )
        await _open_report(
            principal, project, report_type=report_type,
            title=f"Severe {gate_key} breach at {definition['name']}",
            details={"gate": gate_key, "explanation": explanation,
                     "readings": payload.readings},
            stage_instance_id=instance["_id"],
        )
        target_key = recovery.get("target")
        if recovery.get("action") == "return_to_stage" and target_key:
            # v2.0 §4-C: a severe hard-gate breach returns the project to an
            # earlier stage for redesign, automatically — never a verbal pass.
            await _rollback_to(principal, project, definition, target_key, explanation)
            rolled_to = target_key
        else:
            # v1.0 semantics: a severe breach halts the whole project (§8).
            # Stamped `engine` so resolving the recovery report auto-clears it.
            await repo.update(db, repo.PROJECTS, project["_id"], {
                "status": "on_hold",
                "hold": {"source": "engine", "at": _now(),
                         "reason": f"severe gate breach: {gate_key}"},
            })

    await _log(principal, "gate.passed" if passed else "gate.failed",
               {"type": "project", "id": project_id, "label": project["name"]},
               {"stage": definition["key"], "gate": gate_key,
                "passed": passed, "severe": severe, "explanation": explanation})
    final_instance = await repo.stage_instance(db, project["_id"], order)
    return {
        "result": result,
        "instance": final_instance or engine_result["instance"],
        "project_status": (
            "active" if rolled_to else "on_hold" if severe else project["status"]
        ),
        "rolled_back_to": rolled_to,
    }


async def waive_gate(
    principal: ClientPrincipal, project_id: str, order: int,
    gate_key: str, payload: GateWaive,
) -> dict:
    """SOP §3 — a hard gate may be waived, in writing, **only** by the
    `project_director`. Modelled as a passing gate result with provenance
    (`waived:true`, reason, waived_by): because `evaluate_stage` treats any
    passing gate result as satisfied, the waiver clears the gate with no engine
    change, and the record surfaces in the Stage-9 technical defence file."""
    project = await _project(principal, project_id)
    definition = await _definition(principal, project, order)
    db = principal.tenant_db
    instance = await repo.stage_instance(db, project["_id"], order)
    if instance is None:
        raise DomainError(TENANT_NOT_FOUND, f"Stage {order} not reached.", 404)

    # The threshold is the one THIS project pinned — another configuration may
    # define the same gate with a different tolerance (G-3, G-5).
    rule = await repo.gate_rule(db, gate_key, await repo.scope_for_project(db, project))
    if rule is None:
        raise DomainError(TENANT_NOT_FOUND, f"Gate '{gate_key}' is not defined.", 404)
    if not rule.get("blocking", True):
        raise DomainError(
            VALIDATION_ERROR,
            f"Gate '{gate_key}' is not a blocking gate — there is nothing to waive.",
            http_status=422,
        )
    attach = rule.get("attach_to_stages") or []
    if attach and definition["key"] not in attach:
        raise DomainError(
            VALIDATION_ERROR,
            f"Gate '{gate_key}' does not attach to stage '{definition['key']}'.",
            http_status=422,
        )

    # director-only: the caller must hold the `project_director` position — plain
    # `projects` WRITE is not enough (SOP §3).
    allowed = await engines.may_approve(
        db, "project_director", str(principal.user["_id"]),
        principal.role.get("name", ""),
    )
    if not allowed:
        raise DomainError(
            PERMISSION_DENIED,
            "Only the project_director may waive a hard gate.",
            http_status=403,
        )

    result = await repo.insert(db, repo.GATE_RESULTS, {
        "stage_instance_id": instance["_id"],
        "project_id": project["_id"],
        "gate_key": gate_key,
        "type": rule.get("type"),
        "captured_by": str(principal.user["_id"]),
        "captured_at": _now(),
        "readings": [],
        "checklist_results": [],
        "threshold": rule.get("threshold"),
        "passed": True,
        "severe": False,
        "waived": True,
        "reason": payload.reason,
        "waived_by": str(principal.user["_id"]),
        "explanation": f"Gate waived by project_director: {payload.reason}",
        "notes": None,
    })

    instance = await repo.stage_instance(db, project["_id"], order)
    assert instance is not None
    engine_result = await engines.run_decision_engine(db, project, definition, instance)
    await _log(principal, "gate.waived",
               {"type": "project", "id": project_id, "label": project["name"]},
               {"stage": definition["key"], "gate": gate_key,
                "reason": payload.reason})
    return {"result": result, "instance": engine_result["instance"]}


async def mark_checklist_section(
    principal: ClientPrincipal, project_id: str, order: int,
    section: str, payload: ChecklistMark,
) -> dict:
    """v2.0 Stage 6 · Factory Release (§5-C): mark one release-checklist section
    complete (or reopen it). `run_auto_validation` blocks release until every
    seeded section is complete."""
    project = await _project(principal, project_id)
    definition = await _definition(principal, project, order)
    db = principal.tenant_db
    instance = await repo.stage_instance(db, project["_id"], order)
    if instance is None:
        raise DomainError(TENANT_NOT_FOUND, f"Stage {order} not reached.", 404)

    sections = definition.get("release_checklist") or []
    if section not in sections:
        raise DomainError(
            VALIDATION_ERROR,
            f"Stage '{definition['key']}' has no release-checklist section '{section}'.",
            http_status=422,
        )

    done = set(instance.get("checklist_done") or [])
    if payload.complete:
        done.add(section)
    else:
        done.discard(section)
    await repo.set_stage_fields(db, instance["_id"], {"checklist_done": sorted(done)})
    instance = await repo.stage_instance(db, project["_id"], order)
    await _log(principal, "stage.checklist_marked",
               {"type": "project", "id": project_id, "label": project["name"]},
               {"stage": definition["key"], "section": section,
                "complete": payload.complete})
    return instance  # type: ignore[return-value]


async def record_client_acceptance(
    principal: ClientPrincipal, project_id: str, payload: ClientAcceptanceCreate
) -> dict:
    """v2.0 Stage 9 (SOP §9): record a written client acceptance so the handover
    may proceed with an open snag. Stored on the project with who/when."""
    project = await _project(principal, project_id)
    acceptance = {
        "note": payload.note,
        "by": str(principal.user["_id"]),
        "at": _now(),
    }
    updated = await repo.update(
        principal.tenant_db, repo.PROJECTS, project["_id"],
        {"client_acceptance": acceptance},
    )
    assert updated is not None
    await _log(principal, "project.client_acceptance",
               {"type": "project", "id": project_id, "label": project["name"]},
               {"note": payload.note})
    return updated


async def run_task(
    principal: ClientPrincipal, project_id: str, order: int, task_key: str
) -> dict:
    """§6 — re-run the decision engine. Deterministic and idempotent."""
    project = await _project(principal, project_id)
    definition = await _definition(principal, project, order)
    db = principal.tenant_db
    instance = await repo.stage_instance(db, project["_id"], order)
    if instance is None:
        raise DomainError(TENANT_NOT_FOUND, f"Stage {order} not reached.", 404)
    if task_key not in (definition.get("automated_tasks") or []):
        raise DomainError(
            VALIDATION_ERROR, f"Stage {order} has no task '{task_key}'.", 422
        )
    result = await engines.run_decision_engine(db, project, definition, instance)

    # §6.2: a stage starved of documents raises a Missing Information report.
    # v2.0: entry documents live on Stage 1 (project_initiation), so that is the
    # stage whose starvation raises the report (report_types → project_initiation).
    if result["evaluation"]["waiting_on"] and definition["key"] == "project_initiation":
        await _open_report(
            principal, project, report_type="missing_information",
            title=f"Missing information at {definition['name']}",
            details={"waiting_on": result["evaluation"]["waiting_on"]},
            stage_instance_id=instance["_id"], dedupe=True,
        )
    return result


async def submit_stage(
    principal: ClientPrincipal, project_id: str, order: int, note: str | None
) -> dict:
    """§5.1–5.2: draft → automated validation.

    A failure short-circuits to an Issue Report and returns the stage to
    in_progress; it never reaches an approver.
    """
    project = await _project(principal, project_id)
    definition = await _definition(principal, project, order)
    db = principal.tenant_db
    instance = await repo.stage_instance(db, project["_id"], order)
    if instance is None:
        raise DomainError(TENANT_NOT_FOUND, f"Stage {order} not reached.", 404)
    if instance["status"] == "approved":
        raise DomainError(VALIDATION_ERROR, "Stage is already approved.", 409)
    if instance["status"] == "on_hold":
        raise DomainError(
            VALIDATION_ERROR,
            "Stage is on hold; resolve the open report before resubmitting.", 409,
        )

    approval = await engines.open_or_create_approval(
        db, project, definition, instance, str(principal.user["_id"])
    )
    await repo.set_stage_fields(db, instance["_id"], {
        "status": "validation", "approval_id": approval["_id"],
    })
    await db[repo.APPROVALS].update_one(
        {"_id": approval["_id"]}, {"$set": {"state": "auto_validation"}}
    )

    validation = await engines.run_auto_validation(db, project, definition, instance)
    await db[repo.APPROVALS].update_one(
        {"_id": approval["_id"]},
        {"$set": {"auto_validation": {
            "passed": validation["passed"], "checks": validation["checks"],
            "at": _now(),
        }}},
    )

    if not validation["passed"]:
        failed = [c for c in validation["checks"] if not c["passed"]]
        report = await _open_report(
            principal, project, report_type="issue",
            title=f"Automated validation failed at {definition['name']}",
            details={"failed_checks": failed},
            stage_instance_id=instance["_id"], dedupe=True,
        )
        await db[repo.APPROVALS].update_one(
            {"_id": approval["_id"]},
            {"$set": {"state": "draft", "change_report_id": report["_id"]}},
        )
        instance = await repo.stage_instance(db, project["_id"], order)
        assert instance is not None
        engine_result = await engines.run_decision_engine(db, project, definition, instance)
        await _log(principal, "stage.submitted",
                   {"type": "project", "id": project_id, "label": project["name"]},
                   {"stage": definition["key"], "validation": "failed",
                    "report_id": str(report["_id"])})
        return {
            "validation": validation, "approved": False,
            "instance": engine_result["instance"], "report": report,
        }

    # v2.0 §4-A: an auto-advancing stage (no approver_role) advances on completion
    # rather than parking in pending_approval for a manager decision.
    if definition.get("auto_advance") or definition.get("approver_role") is None:
        await _log(principal, "stage.auto_advanced",
                   {"type": "project", "id": project_id, "label": project["name"]},
                   {"stage": definition["key"], "validation": "passed", "note": note})
        result = await _finalize_stage(
            principal, project, definition, instance, decision_by="system",
        )
        return {"validation": validation, "auto_advanced": True, **result}

    await db[repo.APPROVALS].update_one(
        {"_id": approval["_id"]}, {"$set": {"state": "manager_review"}}
    )
    updated = await repo.set_stage_fields(db, instance["_id"], {
        "status": "pending_approval",
    })
    await _log(principal, "stage.submitted",
               {"type": "project", "id": project_id, "label": project["name"]},
               {"stage": definition["key"], "validation": "passed",
                "approver_role": definition.get("approver_role"), "note": note})
    return {"validation": validation, "approved": False, "instance": updated,
            "approval": await repo.approval(db, approval["_id"])}


async def _assert_may_approve(
    principal: ClientPrincipal, definition: dict
) -> None:
    """§9: the caller must hold the stage's approver_role (resolved through the
    Settings-editable approver map). `projects` WRITE alone never suffices."""
    db = principal.tenant_db
    approver_role = definition.get("approver_role") or ""
    role_name = principal.role.get("name", "")

    allowed = await engines.may_approve(
        db, approver_role, str(principal.user["_id"]), role_name
    )
    if not allowed:
        raise DomainError(
            PERMISSION_DENIED,
            f"Approving this stage requires the '{approver_role}' position.",
            http_status=403,
        )


async def _finalize_stage(
    principal: ClientPrincipal, project: dict, definition: dict, instance: dict,
    *, decision_by: str, comment: str | None = None,
) -> dict:
    """Mark a stage approved and move the project on — the shared tail of a
    manager approval (§5.4) and an auto-advancing stage (v2.0 Stage 2, §4-A).

    §1: integrations run HERE, before anything is marked approved, so a failing
    side effect (e.g. Inventory INSUFFICIENT_STOCK at Stage 5) raises and leaves
    the stage recoverable rather than approved-with-no-effect. `decision_by ==
    "system"` marks the auto-advance path.
    """
    db = principal.tenant_db
    order = int(definition["order"])
    scope = await repo.scope_for_project(db, project)

    # Fail BEFORE any mutation if this project's pinned configuration isn't seeded —
    # else the approval marks the stage done but can't open what it unlocks,
    # stranding the project (a tenant not yet migrated, or a version whose
    # definitions were pruned out from under a live project).
    if not await repo.stage_defs(db, scope):
        raise DomainError(
            VALIDATION_ERROR,
            f"The '{project.get('workflow_type', 'sequential')}' workflow is not "
            "seeded on this workspace — re-seed the Projects module "
            "(scripts/migrate_projects_v4.py) before approving stages.",
            409,
        )

    auto = decision_by == "system"
    integration = await _run_integrations(principal, project, definition)

    approval = await repo.open_approval(db, instance["_id"])
    if approval is not None:
        await db[repo.APPROVALS].update_one(
            {"_id": approval["_id"]},
            {"$set": {"state": "approved", "decision": {
                "by": decision_by, "at": _now(), "comment": comment,
            }}},
        )
    await repo.set_stage_fields(db, instance["_id"], {"status": "approved"})

    history = list(project.get("stage_history") or [])
    history.append({
        "order": order, "key": definition["key"],
        "entered_at": instance.get("entered_at"), "exited_at": _now(),
        "result": "auto_advanced" if auto else "approved",
    })

    fields: dict[str, Any] = {"stage_history": history}
    if order >= LAST_STAGE_ORDER:
        fields.update({"status": "completed", "completed_at": _now()})
        await repo.update(db, repo.PROJECTS, project["_id"], fields)
        await _log(principal, "project.completed",
                   {"type": "project", "id": str(project["_id"]), "label": project["name"]},
                   {"code": project["code"]})
        return {
            "stage": "approved", "project_status": "completed",
            "handover": integration.get("handover"), "next_stage": None,
            "integration": integration,
        }

    # Persist history, then open every stage this approval unlocked — exactly the
    # next one for a sequential project, possibly several for a concurrent one.
    updated = await repo.update(db, repo.PROJECTS, project["_id"], fields)
    assert updated is not None
    newly = await _enter_unlocked_stages(principal, updated)

    # Point the single representative cursor at the lowest-order stage still in
    # flight (entered, not yet approved); fall back to the stage just approved.
    defs_by_order = {int(d["order"]): d for d in await repo.stage_defs(db, scope)}
    instances = await repo.stage_instances(db, updated["_id"])
    active = sorted(
        int(i["stage_order"]) for i in instances if i.get("status") != "approved"
    )
    rep = active[0] if active else order
    rep_def = defs_by_order.get(rep) or definition
    updated = await repo.update(db, repo.PROJECTS, updated["_id"], {
        "current_stage_order": rep, "current_stage_key": rep_def["key"],
    })
    assert updated is not None
    return {
        "stage": "approved", "project_status": updated["status"],
        "integration": integration,
        # `next_stage` stays the (single) next for sequential callers; `next_stages`
        # carries the full set a concurrent approval opened.
        "next_stage": (
            {"order": int(newly[0][0]["order"]), "key": newly[0][0]["key"],
             "status": newly[0][1]["status"]} if newly else None
        ),
        "next_stages": [
            {"order": int(d["order"]), "key": d["key"], "status": inst["status"]}
            for d, inst in newly
        ],
    }


async def approve_stage(
    principal: ClientPrincipal, project_id: str, order: int, comment: str | None
) -> dict:
    """§5.4 — approved → stage approved, project moves to the next stage."""
    project = await _project(principal, project_id)
    definition = await _definition(principal, project, order)
    await _assert_may_approve(principal, definition)

    db = principal.tenant_db
    instance = await repo.stage_instance(db, project["_id"], order)
    if instance is None:
        raise DomainError(TENANT_NOT_FOUND, f"Stage {order} not reached.", 404)
    if instance["status"] != "pending_approval":
        raise DomainError(
            VALIDATION_ERROR,
            f"Stage is {instance['status']}; submit it for approval first.", 409,
        )

    # re-run validation at the decision point: state may have moved since submit
    validation = await engines.run_auto_validation(db, project, definition, instance)
    if not validation["passed"]:
        raise DomainError(
            VALIDATION_ERROR,
            "Stage no longer passes automated validation; resubmit it.",
            http_status=409,
            details={"failed": [c for c in validation["checks"] if not c["passed"]]},
        )

    await _log(principal, "stage.approved",
               {"type": "project", "id": project_id, "label": project["name"]},
               {"stage": definition["key"], "order": order, "comment": comment})
    return await _finalize_stage(
        principal, project, definition, instance,
        decision_by=str(principal.user["_id"]), comment=comment,
    )


async def _rollback_to(
    principal: ClientPrincipal, project: dict, definition: dict,
    target_key: str, reason: str | None,
) -> None:
    """Return the project to an earlier stage (v2.0 §4-C): the current stage is
    abandoned (`rejected`), the target stage is reopened and re-evaluated, and the
    project is taken off any hold. Callers own the recovery report. Used by both a
    severe hard-gate breach (auto) and a return_to_stage rejection (manual)."""
    db = principal.tenant_db
    order = int(definition["order"])
    current = await repo.stage_instance(db, project["_id"], order)
    if current is not None:
        await repo.set_stage_fields(db, current["_id"], {
            "status": "rejected", "blocking_reason": reason,
        })
    target_def = await repo.stage_def_by_key(
        db, target_key, await repo.scope_for_project(db, project)
    )
    if target_def is not None:
        await repo.update(db, repo.PROJECTS, project["_id"], {
            "status": "active",
            "current_stage_order": target_def["order"],
            "current_stage_key": target_def["key"],
        })
        reopened = await repo.get(db, repo.PROJECTS, project["_id"])
        target_instance = await repo.stage_instance(db, project["_id"], target_def["order"])
        if reopened is not None and target_instance is not None:
            await repo.set_stage_fields(db, target_instance["_id"], {
                "status": "in_progress", "blocking_reason": None,
            })
            target_instance = await repo.stage_instance(db, project["_id"], target_def["order"])
            assert target_instance is not None
            await engines.run_decision_engine(db, reopened, target_def, target_instance)
    await _log(principal, "stage.rolled_back",
               {"type": "project", "id": str(project["_id"]), "label": project["name"]},
               {"from": definition["key"], "to": target_key, "reason": reason})


async def reject_stage(
    principal: ClientPrincipal, project_id: str, order: int,
    comment: str, report_type: str | None, owner_id: str | None,
) -> dict:
    """§5.5 — generate the typed report, assign an owner, increment
    recovery_loops, reopen the stage (acceptance #5)."""
    project = await _project(principal, project_id)
    definition = await _definition(principal, project, order)
    await _assert_may_approve(principal, definition)

    db = principal.tenant_db
    instance = await repo.stage_instance(db, project["_id"], order)
    if instance is None:
        raise DomainError(TENANT_NOT_FOUND, f"Stage {order} not reached.", 404)
    if instance["status"] not in ("pending_approval", "validation"):
        raise DomainError(
            VALIDATION_ERROR,
            f"Stage is {instance['status']}; there is nothing awaiting a decision.",
            http_status=409,
        )

    recovery = definition.get("recovery") or {}
    chosen = report_type or recovery.get("report_type") or DEFAULT_REJECT_REPORT
    report = await _open_report(
        principal, project, report_type=chosen,
        title=f"{definition['name']} rejected",
        details={"comment": comment, "stage": definition["key"], "order": order},
        stage_instance_id=instance["_id"],
        owner_id=owner_id,
    )

    approval = await repo.open_approval(db, instance["_id"])
    if approval is not None:
        await db[repo.APPROVALS].update_one(
            {"_id": approval["_id"]},
            {"$set": {
                "state": "rejected",
                "decision": {"by": str(principal.user["_id"]), "at": _now(),
                             "comment": comment},
                "change_report_id": report["_id"],
            }},
        )

    loops = await engines.bump_recovery(db, instance["_id"])

    # v2.0 §4-C: a recovery may return the project to an EARLIER stage (a severe
    # G1 deviation at Stage 4 → back to Stage 3 for redesign) instead of holding
    # or reopening the current stage.
    target_key = recovery.get("target")
    target_def = (
        await repo.stage_def_by_key(
            db, target_key, await repo.scope_for_project(db, project)
        )
        if recovery.get("action") == "return_to_stage" and target_key else None
    )
    rollback = target_def is not None and int(target_def["order"]) < order
    hold = recovery.get("state") == "on_hold"

    if rollback:
        assert target_def is not None
        await _rollback_to(principal, project, definition, target_def["key"], comment)
    elif hold:
        await repo.set_stage_fields(db, instance["_id"], {
            "status": "on_hold", "blocking_reason": comment,
        })
        await repo.update(db, repo.PROJECTS, project["_id"], {
            "status": "on_hold",
            "hold": {"source": "engine", "at": _now(), "reason": comment},
        })
    else:
        # the rejection reopens the same stage for a mandatory resubmission loop
        await repo.set_stage_fields(db, instance["_id"], {
            "status": "in_progress", "blocking_reason": comment,
        })
        reopened_instance = await repo.stage_instance(db, project["_id"], order)
        assert reopened_instance is not None
        await engines.run_decision_engine(db, project, definition, reopened_instance)

    await _log(principal, "stage.rejected",
               {"type": "project", "id": project_id, "label": project["name"]},
               {"stage": definition["key"], "comment": comment,
                "report_type": chosen, "recovery_loops": loops})
    final = await repo.stage_instance(db, project["_id"], order)
    return {"instance": final, "report": report, "recovery_loops": loops}


# --- integrations (§1) -------------------------------------------------------

async def _run_integrations(
    principal: ClientPrincipal, project: dict, definition: dict
) -> dict:
    """Stage-specific calls into CRM/Inventory/Finance (§1, acceptance #7/#8).

    Kept explicit: PM triggers the other module's service and records what it
    did — no hidden side effects (INVENTORY.md §5).
    """
    key = definition["key"]
    if key == "material_procurement":  # Stage 5 (G2)
        return {"reservations": await _reserve_stock(principal, project)}
    if key == "final_inspection_handover":  # Stage 9 (terminal)
        return {"handover": await _build_handover(principal, project)}
    return {}


async def _reserve_stock(principal: ClientPrincipal, project: dict) -> list[dict]:
    """Stage 8 (§7/§15): reserve BOM stock through Inventory.

    §1 says PM reserves "via Inventory movements". Inventory has no reservation
    primitive (its types are receipt/issue/transfer/adjustment), so a reservation
    IS an issue against the project: the stock leaves general availability and is
    allocated here. Stage 9 then reports actuals as job costs rather than moving
    stock again, so nothing is double-counted.
    """
    from app.modules.inventory import service as inv_service
    from app.modules.inventory.models import MovementCreate

    db = principal.tenant_db
    # The reservable BOM is the one carrying product lines. A BOM *document*
    # attached at the `bom_present` gate is just a file (kind `bom`, no lines),
    # so it must never shadow the real one — match on a non-empty `lines` and
    # take the newest.
    bom = await db[repo.DELIVERABLES].find_one(
        {"project_id": project["_id"], "kind": "bom", "is_deleted": {"$ne": True},
         "lines.0": {"$exists": True}},
        sort=[("created_at", -1)],
    )
    if bom is None:
        return []
    lines = bom["lines"]

    from app.modules.inventory import repository as inv_repo

    warehouse = await db[inv_repo.WAREHOUSES].find_one(
        {"is_deleted": {"$ne": True}}, sort=[("code", 1)]
    )
    if warehouse is None:
        raise DomainError(VALIDATION_ERROR, "No warehouse to reserve stock from.", 409)

    reserved: list[dict] = []
    committed_value = 0.0
    try:
        for line in lines:
            product = await db[inv_repo.PRODUCTS].find_one(
                {"_id": ObjectId(str(line["product_id"]))}
            )
            movement = await inv_service.create_movement(principal, MovementCreate(
                product_id=str(line["product_id"]),
                warehouse_id=str(warehouse["_id"]),
                type="issue",
                qty=float(line["qty"]),
                note=f"Reserved for {project['code']}",
                ref_module="projects",
                ref_doc_id=str(project["_id"]),
            ))
            line_value = float((product or {}).get("cost_price") or 0) * float(line["qty"])
            committed_value += line_value
            reserved.append({
                "product_id": str(line["product_id"]),
                "qty": float(line["qty"]),
                "value": round(line_value, 2),
                "movement_id": str(movement["_id"]),
            })
    except Exception:
        for done in reserved:
            await _release_movement(principal, done["movement_id"])
        raise

    # §7/acceptance #7: the reservation is a commitment against the budget. It
    # converts to actual when Stage 9 records the material job cost, so the two
    # never double-count.
    if committed_value:
        current = await repo.get(db, repo.PROJECTS, project["_id"])
        budget = dict((current or project).get("budget") or {})
        budget["committed"] = round(float(budget.get("committed") or 0) + committed_value, 2)
        await repo.update(db, repo.PROJECTS, project["_id"], {"budget": budget})

    await _log(principal, "project.stock_reserved",
               {"type": "project", "id": str(project["_id"]), "label": project["name"]},
               {"lines": len(reserved), "committed": round(committed_value, 2)})
    return reserved


async def _release_movement(principal: ClientPrincipal, movement_id: str) -> None:
    from app.modules.inventory import repository as inv_repo

    db = principal.tenant_db
    movement = await db[inv_repo.MOVEMENTS].find_one({"_id": ObjectId(movement_id)})
    if movement is None:
        return
    await inv_repo.release_stock(
        db, movement["product_id"], movement["warehouse_id"], movement["qty"]
    )
    await db[inv_repo.MOVEMENTS].delete_one({"_id": movement["_id"]})


async def _build_handover(principal: ClientPrincipal, project: dict) -> dict:
    """Stage 16 (§7, acceptance #8): the handover pack + final invoice."""
    from app.modules.finance import service as fin_service
    from app.modules.finance.models import CustomerRef, DocLine, InvoiceCreate

    db = principal.tenant_db
    actor = str(principal.user["_id"])
    defence_title = "Gate Records G1–G5 (Technical Defence File)"

    # SOP §3/§9: any director-waived hard gate is recorded in the defence file
    # alongside the measured readings — a waiver must never be silent.
    waivers = [
        {"gate_key": w["gate_key"], "reason": w.get("reason"),
         "waived_by": w.get("waived_by"), "at": w.get("captured_at")}
        for w in await repo.waived_gate_results(db, project["_id"])
    ]

    pack: list[dict] = []
    for kind, title in (
        ("certificate", "Completion Certificate"),
        ("certificate", "Warranty"),
        ("report", "Operation & Maintenance Manuals"),
        ("shop_drawing", "As-built Drawings"),
        # SOP §9: the technical defence file — the hard-gate readings that back
        # the warranty (G1 deviation, G3 concrete RH, G4 flatness, G5 timber MC)
        # plus any recorded gate waivers.
        ("report", defence_title),
    ):
        is_defence = title == defence_title
        doc = await repo.insert(db, repo.DELIVERABLES, {
            "project_id": project["_id"],
            "stage_key": "final_inspection_handover",
            "kind": kind,
            "title": title,
            "current_version": 1,
            "versions": [{"v": 1, "source_type": "url",
                          "file_ref": f"generated:{project['code']}:{title}",
                          "author_id": actor, "at": _now(), "note": "handover pack"}],
            "classification": "auto",
            "ocr_text": None,
            "gate_waivers": waivers if is_defence else [],
            "immutable_audit": [{"action": "created", "by": actor, "at": _now()}],
            "created_by": actor,
        })
        entry: dict[str, Any] = {"id": str(doc["_id"]), "kind": kind, "title": title}
        if is_defence:
            entry["gate_waivers"] = waivers
        pack.append(entry)

    # final invoice for whatever is not yet billed
    invoice: dict | None = None
    budget = project.get("budget") or {}
    total = float(budget.get("planned") or 0)
    if total > 0:
        created = await fin_service.create_invoice(principal, InvoiceCreate(
            customer_ref=CustomerRef(
                crm_account_id=str(project["crm_account_id"])
                if project.get("crm_account_id") else None,
                name=project["name"],
            ),
            due_date=_now(),
            lines=[DocLine(
                description=f"{project['code']} — {project['name']} final account",
                qty=1, unit_price=total, tax_rate=0,
            )],
        ))
        invoice = {"id": str(created["_id"]), "total": created["total"],
                   "status": created["status"]}

    await _log(principal, "project.handover",
               {"type": "project", "id": str(project["_id"]), "label": project["name"]},
               {"documents": len(pack), "final_invoice": bool(invoice),
                "gate_waivers": len(waivers)})
    return {"documents": pack, "final_invoice": invoice, "gate_waivers": waivers}


# --- deliverables (§3.7) -----------------------------------------------------

async def _user_names(db, ids: set[str]) -> dict[str, str | None]:
    """Resolve tenant-user ids → display names for document authorship (§3.7)."""
    oids: list[ObjectId] = []
    for i in ids:
        if not i:
            continue
        try:
            oids.append(ObjectId(i))
        except (InvalidId, TypeError):
            pass
    if not oids:
        return {}
    names: dict[str, str | None] = {}
    async for u in db.users.find({"_id": {"$in": oids}}, {"name": 1}):
        names[str(u["_id"])] = u.get("name")
    return names


def _author_name(names: dict[str, str | None], author_id: str | None) -> str | None:
    """Display name for a version's author, or None when there is no author to
    look up — an empty `versions` list and legacy rows written before authorship
    was recorded both reach here without an `author_id`."""
    return names.get(author_id) if author_id else None


async def _decorate_deliverables(db, docs: list[dict]) -> list[dict]:
    """Add who/when/how a reader wants: an uploader name on each version, plus
    the latest version's uploader, timestamp, and source at the top level.
    Legacy rows without `source_type` read as a URL reference."""
    ids: set[str] = set()
    for d in docs:
        for v in d.get("versions") or []:
            if v.get("author_id"):
                ids.add(v["author_id"])
        if d.get("created_by"):
            ids.add(d["created_by"])
    names = await _user_names(db, ids)
    for d in docs:
        versions = d.get("versions") or []
        for v in versions:
            v.setdefault("source_type", "url")
            v["author_name"] = _author_name(names, v.get("author_id"))
        latest = versions[-1] if versions else {}
        d["source_type"] = latest.get("source_type", "url")
        d["uploaded_by"] = _author_name(names, latest.get("author_id"))
        d["uploaded_at"] = latest.get("at")
    return docs


async def _resolve_doc_stage(
    principal: ClientPrincipal, project: dict, stage_key: str | None
) -> str | None:
    """A document may belong to a stage or be a general project doc (None). A
    provided stage must be a real stage key in the project's own configuration."""
    if not stage_key:
        return None
    db = principal.tenant_db
    scope = await repo.scope_for_project(db, project)
    if await repo.stage_def_by_key(db, stage_key, scope) is None:
        raise DomainError(VALIDATION_ERROR, f"Unknown stage '{stage_key}'.", 422)
    return stage_key


async def _make_version(db, *, v: int, payload, author: str, note: str) -> dict:
    """Build one document version from an upload (GridFS) or a URL reference."""
    version: dict[str, Any] = {
        "v": v, "source_type": payload.source_type, "author_id": author,
        "at": _now(), "note": note,
    }
    if payload.source_type == "upload":
        meta = await storage.file_metadata(db, payload.file_id)
        if meta is None:
            raise DomainError(
                TENANT_NOT_FOUND, "Uploaded file not found — upload it first.", 404
            )
        version.update({
            "file_id": meta.file_id, "filename": meta.filename,
            "content_type": meta.content_type, "size": meta.size,
            "file_ref": meta.filename,
        })
    else:
        version.update({
            "file_id": None, "filename": None, "content_type": None,
            "size": None, "file_ref": payload.file_ref,
        })
    return version


async def store_deliverable_file(
    principal: ClientPrincipal, project_id: str, upload
) -> dict:
    """Persist an uploaded file in the tenant GridFS and return its handle; the
    caller then creates/revises a document referencing the returned file_id."""
    await _project(principal, project_id)
    stored = await storage.save_upload(
        principal.tenant_db, upload,
        uploaded_by=str(principal.user["_id"]),
        max_bytes=settings.max_upload_mb * 1024 * 1024,
    )
    return {
        "file_id": stored.file_id, "filename": stored.filename,
        "content_type": stored.content_type, "size": stored.size,
    }


async def open_deliverable_file(
    principal: ClientPrincipal, project_id: str, deliverable_id: str,
    version: int | None,
):
    """Open the GridFS stream for a document version's uploaded file (download).
    URL-reference versions have no file to stream."""
    project = await _project(principal, project_id, mutating=False)
    db = principal.tenant_db
    deliverable = await db[repo.DELIVERABLES].find_one({
        "_id": _oid(deliverable_id, "Deliverable"),
        "project_id": project["_id"], "is_deleted": {"$ne": True},
    })
    if deliverable is None:
        raise DomainError(TENANT_NOT_FOUND, "Document not found.", 404)
    versions = deliverable.get("versions") or []
    if version is None:
        ver = versions[-1] if versions else None
    else:
        ver = next((v for v in versions if int(v.get("v", 0)) == version), None)
    if ver is None:
        raise DomainError(TENANT_NOT_FOUND, f"Version {version} not found.", 404)
    if ver.get("source_type") != "upload" or not ver.get("file_id"):
        raise DomainError(
            VALIDATION_ERROR,
            "This version is a URL reference, not an uploaded file.", 422,
        )
    return await storage.open_download(db, ver["file_id"])


async def list_deliverables(
    principal: ClientPrincipal, project_id: str, kind: str | None,
    skip: int, limit: int,
) -> tuple[list[dict], int]:
    project = await _project(principal, project_id, mutating=False)
    query: dict[str, Any] = {"project_id": project["_id"]}
    if kind:
        query["kind"] = kind
    docs, total = await repo.list_docs(
        principal.tenant_db, repo.DELIVERABLES, query, skip, limit
    )
    return await _decorate_deliverables(principal.tenant_db, docs), total


async def create_deliverable(
    principal: ClientPrincipal, project_id: str, payload: DeliverableCreate
) -> dict:
    project = await _project(principal, project_id)
    db = principal.tenant_db
    actor = str(principal.user["_id"])
    stage_key = await _resolve_doc_stage(principal, project, payload.stage_key)
    version = await _make_version(
        db, v=1, payload=payload, author=actor, note=payload.note or "initial"
    )
    doc = await repo.insert(db, repo.DELIVERABLES, {
        "project_id": project["_id"],
        "stage_key": stage_key,
        "kind": payload.kind,
        "title": payload.title,
        "current_version": 1,
        "versions": [version],
        "classification": payload.classification,
        "ocr_text": payload.ocr_text,
        "lines": [line.model_dump() for line in payload.lines],
        "immutable_audit": [{"action": "created", "by": actor, "at": _now()}],
        "created_by": actor,
    })
    await _log(principal, "deliverable.created",
               {"type": "deliverable", "id": str(doc["_id"]), "label": doc["title"]},
               {"project": project["code"], "kind": payload.kind})
    return (await _decorate_deliverables(db, [doc]))[0]


def _gate_label(gate_key: str) -> str:
    """`contract_signed` → `Contract signed` — a document gate's own label is a
    good default title for the evidence attached to it."""
    words = gate_key.replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else gate_key


async def attach_gate_document(
    principal: ClientPrincipal, project_id: str, order: int, gate_key: str,
    payload: GateDocumentAttach,
) -> dict:
    """§4 — attach the evidence a document gate requires (an uploaded file or a
    URL) and satisfy the gate in one step.

    The gate defines both the document's kind and its stage, so neither is asked
    for: the kind is derived from the gate and the stage is the gate's own.
    """
    project = await _project(principal, project_id)
    definition = await _definition(principal, project, order)
    db = principal.tenant_db

    gate = next(
        (g for g in (definition.get("entry_gates") or []) if g.get("key") == gate_key),
        None,
    )
    if gate is None:
        raise DomainError(
            VALIDATION_ERROR, f"Stage {order} has no entry gate '{gate_key}'.", 422
        )
    if gate.get("type") != "document":
        raise DomainError(
            VALIDATION_ERROR,
            f"Gate '{gate_key}' does not take a document — it is a "
            f"{gate.get('type')} gate.",
            422,
        )

    actor = str(principal.user["_id"])
    version = await _make_version(
        db, v=1, payload=payload, author=actor,
        note=payload.note or f"attached at {gate_key}",
    )
    doc = await repo.insert(db, repo.DELIVERABLES, {
        "project_id": project["_id"],
        "stage_key": definition["key"],
        "gate_key": gate_key,  # what this document satisfies
        "kind": GATE_DOCUMENT_KINDS.get(gate_key, DEFAULT_GATE_DOCUMENT_KIND),
        "title": payload.title or _gate_label(gate_key),
        "current_version": 1,
        "versions": [version],
        "classification": "manual",
        "ocr_text": None,
        "lines": [],
        "immutable_audit": [{"action": "created", "by": actor, "at": _now()}],
        "created_by": actor,
    })
    await _log(principal, "deliverable.created",
               {"type": "deliverable", "id": str(doc["_id"]), "label": doc["title"]},
               {"project": project["code"], "gate": gate_key, "stage": definition["key"]})

    instance = await supply_document(
        principal, project_id, order, gate_key,
        DocumentSupply(deliverable_id=str(doc["_id"])),
    )
    return {
        "instance": instance,
        "document": (await _decorate_deliverables(db, [doc]))[0],
    }


async def add_revision(
    principal: ClientPrincipal, project_id: str, deliverable_id: str,
    payload: RevisionCreate,
) -> dict:
    """Acceptance #6: every revision is kept; no version is overwritten.

    $push only — there is deliberately no path that mutates or removes an
    existing version or audit row.
    """
    project = await _project(principal, project_id)
    db = principal.tenant_db
    oid = _oid(deliverable_id, "Deliverable")
    deliverable = await db[repo.DELIVERABLES].find_one({
        "_id": oid, "project_id": project["_id"], "is_deleted": {"$ne": True},
    })
    if deliverable is None:
        raise DomainError(TENANT_NOT_FOUND, "Deliverable not found.", 404)

    actor = str(principal.user["_id"])
    next_v = int(deliverable["current_version"]) + 1
    version = await _make_version(
        db, v=next_v, payload=payload, author=actor,
        note=payload.note or f"revision {next_v}",
    )
    await db[repo.DELIVERABLES].update_one(
        {"_id": oid},
        {
            "$push": {
                "versions": version,
                "immutable_audit": {"action": "revised", "by": actor, "at": _now()},
            },
            "$set": {"current_version": next_v, "updated_at": _now()},
        },
    )
    updated = await db[repo.DELIVERABLES].find_one({"_id": oid})
    assert updated is not None
    await _log(principal, "deliverable.revised",
               {"type": "deliverable", "id": deliverable_id,
                "label": updated["title"]},
               {"project": project["code"], "version": next_v})
    return (await _decorate_deliverables(db, [updated]))[0]


# --- reports (§3.8) ----------------------------------------------------------

async def _open_report(
    principal: ClientPrincipal, project: dict, report_type: str, title: str,
    details: dict, stage_instance_id: ObjectId | None = None,
    owner_id: str | None = None, dedupe: bool = False,
) -> dict:
    db = principal.tenant_db
    if dedupe:
        existing = await db[repo.REPORTS].find_one({
            "project_id": project["_id"], "type": report_type, "title": title,
            "status": {"$in": OPEN_REPORT_STATUSES}, "is_deleted": {"$ne": True},
        })
        if existing is not None:
            return existing
    doc = await repo.insert(db, repo.REPORTS, {
        "project_id": project["_id"],
        "stage_instance_id": stage_instance_id,
        "type": report_type,
        "title": title,
        "details": details,
        "owner_id": owner_id or project.get("pm_id") or str(principal.user["_id"]),
        "status": "open",
        "resolved_at": None,
        "created_by": str(principal.user["_id"]),
    })
    await _log(principal, "report.opened",
               {"type": "report", "id": str(doc["_id"]), "label": title},
               {"project": project["code"], "report_type": report_type,
                "owner_id": doc["owner_id"]})
    return doc


async def list_reports(
    principal: ClientPrincipal, project_id: str, type_: str | None,
    status: str | None, skip: int, limit: int,
) -> tuple[list[dict], int]:
    project = await _project(principal, project_id, mutating=False)
    query: dict[str, Any] = {"project_id": project["_id"]}
    if type_:
        query["type"] = type_
    if status:
        query["status"] = status
    return await repo.list_docs(
        principal.tenant_db, repo.REPORTS, query, skip, limit
    )


async def create_report(
    principal: ClientPrincipal, project_id: str, payload: ReportCreate
) -> dict:
    project = await _project(principal, project_id)
    return await _open_report(
        principal, project, report_type=payload.type, title=payload.title,
        details=payload.details,
        stage_instance_id=_oid(payload.stage_instance_id, "Stage instance")
        if payload.stage_instance_id else None,
        owner_id=payload.owner_id,
    )


async def patch_report(
    principal: ClientPrincipal, project_id: str, report_id: str, patch: ReportPatch
) -> dict:
    project = await _project(principal, project_id)
    db = principal.tenant_db
    oid = _oid(report_id, "Report")
    report = await db[repo.REPORTS].find_one({
        "_id": oid, "project_id": project["_id"], "is_deleted": {"$ne": True},
    })
    if report is None:
        raise DomainError(TENANT_NOT_FOUND, "Report not found.", 404)

    fields = {k: v for k, v in patch.model_dump(exclude_unset=True).items() if v is not None}
    if fields.get("status") in ("resolved", "closed"):
        fields["resolved_at"] = _now()
    if not fields:
        return report
    fields["updated_by"] = str(principal.user["_id"])
    await db[repo.REPORTS].update_one({"_id": oid}, {"$set": fields})
    updated = await db[repo.REPORTS].find_one({"_id": oid})
    assert updated is not None

    if fields.get("status") in ("resolved", "closed"):
        await _log(principal, "report.resolved",
                   {"type": "report", "id": report_id, "label": updated["title"]},
                   {"project": project["code"], "report_type": updated["type"]})
        await _maybe_clear_hold(principal, project)
    return updated


async def _maybe_clear_hold(principal: ClientPrincipal, project: dict) -> None:
    """§4: on_hold suspends the project until the recovery report is resolved.

    Only an ENGINE hold auto-clears. A hold a human placed deliberately is
    cleared only by an explicit resume — otherwise resolving an unrelated
    report would silently un-pause a project someone paused on purpose
    (docs/PROJECT_STATUS_PLAN.md §3.3).
    """
    if project.get("status") != "on_hold":
        return
    if (project.get("hold") or {}).get("source") == "manual":
        return
    db = principal.tenant_db
    still_open = await repo.open_reports(db, project["_id"], OPEN_REPORT_STATUSES)
    if still_open:
        return
    await repo.update(db, repo.PROJECTS, project["_id"], {
        "status": "active", "hold": None,
    })
    order = int(project["current_stage_order"])
    instance = await repo.stage_instance(db, project["_id"], order)
    if instance is not None and instance.get("status") == "on_hold":
        # Deliberate override: resolving the recovery report clears the crew to
        # re-work and re-measure. Do NOT re-run the decision engine here — the
        # breaching gate reading is still the latest on record and would snap the
        # stage straight back to on_hold. A fresh gate result (or the next
        # submit) re-evaluates against the new reading.
        await repo.set_stage_fields(db, instance["_id"], {
            "status": "in_progress", "blocking_reason": None,
        })
    await _log(principal, "project.hold_cleared",
               {"type": "project", "id": str(project["_id"]), "label": project["name"]},
               {"code": project["code"]})


# --- job costs (§3.9) --------------------------------------------------------

async def create_job_cost(
    principal: ClientPrincipal, project_id: str, payload: JobCostCreate
) -> dict:
    """Acceptance #7: Stage 9 labor/material actuals post to Finance.

    The cost is captured here and mirrored into the ledger as a balanced manual
    entry (Dr COGS / Cr AP) so the books and the project budget agree.
    """
    project = await _project(principal, project_id)
    db = principal.tenant_db
    amount = round(
        (payload.hours or payload.quantity or 0) * payload.unit_cost, 2
    )
    if amount <= 0:
        raise DomainError(
            VALIDATION_ERROR,
            "A job cost needs hours or quantity and a unit cost.", 422,
        )

    posted_ref: str | None = None
    if payload.post_to_finance:
        from app.modules.finance import repository as fin_repo
        from app.modules.finance import service as fin_service
        from app.modules.finance.models import JournalEntryCreate, JournalLine
        from app.modules.finance.permissions import ACCOUNT_AP, ACCOUNT_COGS

        cogs = await fin_repo.account_by_code(db, ACCOUNT_COGS)
        ap = await fin_repo.account_by_code(db, ACCOUNT_AP)
        if cogs is None or ap is None:
            raise DomainError(
                VALIDATION_ERROR,
                "Chart of accounts is missing COGS or Accounts Payable; "
                "restore them before posting job costs.",
                http_status=409,
            )
        entry = await fin_service.create_entry(principal, JournalEntryCreate(
            memo=f"{project['code']} {payload.cost_type} actual",
            lines=[
                JournalLine(account_id=str(cogs["_id"]), debit=amount,
                            description=payload.description or payload.cost_type),
                JournalLine(account_id=str(ap["_id"]), credit=amount,
                            description=f"{project['code']} accrual"),
            ],
        ))
        posted_ref = str(entry["_id"])

    doc = await repo.insert(db, repo.JOB_COSTS, {
        "project_id": project["_id"],
        "stage_key": payload.stage_key or project["current_stage_key"],
        "cost_type": payload.cost_type,
        "description": payload.description,
        "hours": payload.hours,
        "quantity": payload.quantity,
        "unit_cost": payload.unit_cost,
        "amount": amount,
        "posted_to_finance_ref": posted_ref,
        "captured_at": _now(),
        "created_by": str(principal.user["_id"]),
    })

    # roll the actual into the project budget. A material actual also draws down
    # the Stage-8 commitment (down to zero) so a reserved-then-consumed line is
    # counted once, not twice (acceptance #7).
    budget = dict(project.get("budget") or {})
    budget["actual"] = round(float(budget.get("actual") or 0) + amount, 2)
    if payload.cost_type == "material":
        budget["committed"] = round(
            max(0.0, float(budget.get("committed") or 0) - amount), 2
        )
    await repo.update(db, repo.PROJECTS, project["_id"], {"budget": budget})

    await _log(principal, "project.job_cost",
               {"type": "project", "id": project_id, "label": project["name"]},
               {"cost_type": payload.cost_type, "amount": amount,
                "posted_to_finance": bool(posted_ref)})
    return doc


async def list_job_costs(
    principal: ClientPrincipal, project_id: str, skip: int, limit: int
) -> tuple[list[dict], int]:
    project = await _project(principal, project_id, mutating=False)
    return await repo.list_docs(
        principal.tenant_db, repo.JOB_COSTS, {"project_id": project["_id"]},
        skip, limit,
    )


# --- config (§12) ------------------------------------------------------------
# These browse and tune the tenant's DEFAULT configuration at its current version.
# Phase 2 re-homes them into the per-configuration editor, where a change becomes a
# published version instead of an in-place edit; until then they keep working, and
# they only ever touch the default config — never a version some project has pinned
# other than through that default.

async def list_stage_config(principal: ClientPrincipal) -> list[dict]:
    db = principal.tenant_db
    return await repo.stage_defs(db, await repo.default_scope(db))


async def patch_stage_config(
    principal: ClientPrincipal, key: str, patch: StageConfigPatch
) -> dict:
    db = principal.tenant_db
    scope = await repo.default_scope(db)
    definition = await repo.stage_def_by_key(db, key, scope)
    if definition is None:
        raise DomainError(TENANT_NOT_FOUND, f"Stage '{key}' is not defined.", 404)
    fields = {k: v for k, v in patch.model_dump(exclude_unset=True).items() if v is not None}
    if not fields:
        return definition
    # update the exact doc we read (by _id) — key alone is ambiguous now that the
    # collection carries one stage set per configuration version.
    await db[repo.STAGE_DEFS].update_one({"_id": definition["_id"]}, {"$set": fields})
    updated = await repo.stage_def_by_key(db, key, scope)
    assert updated is not None
    await _log(principal, "projects.stage_config_updated",
               {"type": "stage_definition", "id": key, "label": updated["name"]},
               {"fields": list(fields)})
    return updated


async def list_gate_config(principal: ClientPrincipal) -> list[dict]:
    db = principal.tenant_db
    return await repo.gate_rules(db, await repo.default_scope(db))


async def patch_gate_config(
    principal: ClientPrincipal, key: str, patch: GateConfigPatch
) -> dict:
    """§8: thresholds are seeded defaults, editable per tenant."""
    db = principal.tenant_db
    scope = await repo.default_scope(db)
    rule = await repo.gate_rule(db, key, scope)
    if rule is None:
        raise DomainError(TENANT_NOT_FOUND, f"Gate '{key}' is not defined.", 404)
    fields = {k: v for k, v in patch.model_dump(exclude_unset=True).items() if v is not None}
    if not fields:
        return rule
    # Update the exact doc we read (by _id) — `key` alone is ambiguous now that
    # every configuration version carries its own copy of the gate rules (G-3).
    await db[repo.GATE_RULES].update_one({"_id": rule["_id"]}, {"$set": fields})
    updated = await repo.gate_rule(db, key, scope)
    assert updated is not None
    await _log(principal, "projects.gate_config_updated",
               {"type": "gate_rule", "id": key, "label": key},
               {"fields": list(fields)})
    return updated


async def list_approver_config(principal: ClientPrincipal) -> list[dict]:
    return await repo.approver_map(principal.tenant_db)


# --- approver delegation (SOP §2) --------------------------------------------

async def list_delegations(principal: ClientPrincipal) -> list[dict]:
    return await repo.list_delegations(principal.tenant_db)


async def create_delegation(
    principal: ClientPrincipal, payload: DelegationCreate
) -> dict:
    """SOP §2: an approver delegates their position to a named deputy, in
    writing, for a defined period — recorded and audited.

    Guardrails: only a *native* holder of the position (or the project_director)
    may grant it — a deputy cannot re-delegate; no self-delegation; the deputy
    must be a real tenant user. The "never to the person who executed the work"
    rule is procedural and is not machine-enforced here."""
    db = principal.tenant_db
    actor = str(principal.user["_id"])
    role_name = principal.role.get("name", "")

    if await repo.approver_entry(db, payload.approver_role) is None:
        raise DomainError(
            TENANT_NOT_FOUND,
            f"Approver position '{payload.approver_role}' is not defined.", 404,
        )

    holds = await engines.holds_position(db, payload.approver_role, actor, role_name)
    is_director = await engines.holds_position(db, "project_director", actor, role_name)
    if not (holds or is_director):
        raise DomainError(
            PERMISSION_DENIED,
            f"Only a holder of '{payload.approver_role}' (or the project_director) "
            "may delegate it.", 403,
        )

    if payload.delegate_user_id == actor:
        raise DomainError(
            VALIDATION_ERROR, "An approver cannot delegate to themselves.", 422
        )
    if await db.users.find_one({"_id": _oid(payload.delegate_user_id, "User")}) is None:
        raise DomainError(TENANT_NOT_FOUND, "Delegate user not found.", 404)

    starts = payload.starts_at or _now()
    if payload.ends_at <= starts:
        raise DomainError(
            VALIDATION_ERROR, "The delegation must end after it starts.", 422
        )

    doc = await repo.insert(db, repo.DELEGATIONS, {
        "approver_role": payload.approver_role,
        "delegate_user_id": payload.delegate_user_id,
        "granted_by": actor,
        "reason": payload.reason,
        "starts_at": starts,
        "ends_at": payload.ends_at,
        "revoked": False,
    })
    await _log(principal, "delegation.granted",
               {"type": "delegation", "id": str(doc["_id"]),
                "label": payload.approver_role},
               {"approver_role": payload.approver_role,
                "delegate_user_id": payload.delegate_user_id,
                "ends_at": payload.ends_at.isoformat()})
    return doc


async def revoke_delegation(
    principal: ClientPrincipal, delegation_id: str
) -> dict:
    """Revoke a delegation early (SOP §2). Same guard as granting it."""
    db = principal.tenant_db
    actor = str(principal.user["_id"])
    role_name = principal.role.get("name", "")
    oid = _oid(delegation_id, "Delegation")
    delegation = await repo.get(db, repo.DELEGATIONS, oid)
    if delegation is None:
        raise DomainError(TENANT_NOT_FOUND, "Delegation not found.", 404)

    holds = await engines.holds_position(db, delegation["approver_role"], actor, role_name)
    is_director = await engines.holds_position(db, "project_director", actor, role_name)
    if not (holds or is_director):
        raise DomainError(
            PERMISSION_DENIED,
            "Only a holder of the position (or the project_director) may revoke "
            "this delegation.", 403,
        )

    updated = await repo.update(db, repo.DELEGATIONS, oid, {
        "revoked": True, "revoked_by": actor, "revoked_at": _now(),
    })
    assert updated is not None
    await _log(principal, "delegation.revoked",
               {"type": "delegation", "id": delegation_id,
                "label": delegation["approver_role"]},
               {"approver_role": delegation["approver_role"]})
    return updated
