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

from app.core.audit import write_activity
from app.core.errors import (
    PERMISSION_DENIED,
    TENANT_NOT_FOUND,
    VALIDATION_ERROR,
    DomainError,
)
from app.modules.projects import engines
from app.modules.projects import repository as repo
from app.modules.projects.models import (
    DeliverableCreate,
    DocumentSupply,
    GateConfigPatch,
    GateResultCreate,
    JobCostCreate,
    ProjectCreate,
    ProjectPatch,
    ReportCreate,
    ReportPatch,
    RevisionCreate,
    StageConfigPatch,
)
from app.modules.projects.permissions import (
    DEFAULT_REJECT_REPORT,
    FIRST_STAGE_ORDER,
    LAST_STAGE_ORDER,
    OPEN_REPORT_STATUSES,
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


async def _project(principal: ClientPrincipal, project_id: str) -> dict:
    return await _require(
        principal, repo.PROJECTS, _oid(project_id, "Project"), "Project"
    )


async def _definition(principal: ClientPrincipal, order: int) -> dict:
    definition = await repo.stage_def_by_order(principal.tenant_db, order)
    if definition is None:
        raise DomainError(TENANT_NOT_FOUND, f"Stage {order} is not defined.", 404)
    return definition


# --- projects & portfolio (§12) ----------------------------------------------

async def list_projects(
    principal: ClientPrincipal, status: str | None, pm_id: str | None,
    stage: int | None, skip: int, limit: int,
) -> tuple[list[dict], int]:
    query: dict[str, Any] = {}
    if status:
        query["status"] = status
    if pm_id:
        query["pm_id"] = pm_id
    if stage:
        query["current_stage_order"] = stage
    return await repo.list_docs(
        principal.tenant_db, repo.PROJECTS, query, skip, limit,
        sort=[("current_stage_order", 1), ("created_at", -1)],
    )


async def get_project(principal: ClientPrincipal, project_id: str) -> dict:
    return await _project(principal, project_id)


async def create_project(principal: ClientPrincipal, payload: ProjectCreate) -> dict:
    """Stage 1 (§7): create the record and enter the machine at stage 1.

    §1: the client record itself belongs to CRM — we link, never copy it.
    """
    db = principal.tenant_db
    crm_account_id: ObjectId | None = None
    if payload.crm_account_id:
        from app.modules.crm import repository as crm_repo

        account = await crm_repo.get(
            db, crm_repo.ACCOUNTS, _oid(payload.crm_account_id, "Account")
        )
        if account is None:
            raise DomainError(TENANT_NOT_FOUND, "CRM account not found.", 404)
        crm_account_id = account["_id"]

    first = await _definition(principal, FIRST_STAGE_ORDER)
    code = await repo.next_code(db)
    doc = await repo.insert(db, repo.PROJECTS, {
        "code": code,
        "name": payload.name,
        "scope": payload.scope,
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


async def delete_project(principal: ClientPrincipal, project_id: str) -> None:
    project = await _project(principal, project_id)
    await repo.soft_delete(
        principal.tenant_db, repo.PROJECTS, project["_id"], str(principal.user["_id"])
    )
    await _log(principal, "project.deleted",
               {"type": "project", "id": project_id, "label": project["name"]})


async def timeline(principal: ClientPrincipal, project_id: str) -> dict:
    """§12 — stages + milestones for the Gantt view."""
    project = await _project(principal, project_id)
    db = principal.tenant_db
    definitions = await repo.stage_defs(db)
    instances = {
        i["stage_order"]: i for i in await repo.stage_instances(db, project["_id"])
    }
    return {
        "project_id": project_id,
        # tolerate legacy/partial docs that predate the stage machine
        "code": project.get("code"),
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
    project = await _project(principal, project_id)
    if not project.get("current_stage_order"):
        # a legacy/partial doc never entered the machine — nothing to board
        return {"project_id": project_id, "stage": None, "tasks": [],
                "waiting_on": [], "blocked_by": [], "blocking_reason": None,
                "open_reports": []}
    order = int(project["current_stage_order"])
    definition = await _definition(principal, order)
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
    project = await _project(principal, project_id)
    definition = await _definition(principal, order)
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
    """§4: waiting → in_progress once the missing document is supplied."""
    project = await _project(principal, project_id)
    definition = await _definition(principal, order)
    db = principal.tenant_db
    instance = await repo.stage_instance(db, project["_id"], order)
    if instance is None:
        raise DomainError(TENANT_NOT_FOUND, f"Stage {order} not reached.", 404)

    known = {g["key"] for g in (definition.get("entry_gates") or [])}
    if gate_key not in known:
        raise DomainError(
            VALIDATION_ERROR,
            f"Stage {order} has no entry gate '{gate_key}'.", 422,
        )
    supplied = set(instance.get("documents_supplied") or [])
    supplied.add(gate_key)
    await repo.set_stage_fields(db, instance["_id"], {
        "documents_supplied": sorted(supplied),
    })
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
    definition = await _definition(principal, order)
    db = principal.tenant_db
    instance = await repo.stage_instance(db, project["_id"], order)
    if instance is None:
        raise DomainError(TENANT_NOT_FOUND, f"Stage {order} not reached.", 404)

    rule = await repo.gate_rule(db, gate_key)
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

    # a severe breach halts the project, not just the stage (§8, acceptance #3)
    if severe:
        await repo.update(db, repo.PROJECTS, project["_id"], {"status": "on_hold"})
        await _open_report(
            principal, project,
            report_type=(rule.get("severe_threshold") or {}).get("report_type")
            or (definition.get("recovery") or {}).get("report_type") or "issue",
            title=f"Severe {gate_key} breach at {definition['name']}",
            details={"gate": gate_key, "explanation": explanation,
                     "readings": payload.readings},
            stage_instance_id=instance["_id"],
        )

    await _log(principal, "gate.passed" if passed else "gate.failed",
               {"type": "project", "id": project_id, "label": project["name"]},
               {"stage": definition["key"], "gate": gate_key,
                "passed": passed, "severe": severe, "explanation": explanation})
    return {
        "result": result,
        "instance": engine_result["instance"],
        "project_status": "on_hold" if severe else project["status"],
    }


async def run_task(
    principal: ClientPrincipal, project_id: str, order: int, task_key: str
) -> dict:
    """§6 — re-run the decision engine. Deterministic and idempotent."""
    project = await _project(principal, project_id)
    definition = await _definition(principal, order)
    db = principal.tenant_db
    instance = await repo.stage_instance(db, project["_id"], order)
    if instance is None:
        raise DomainError(TENANT_NOT_FOUND, f"Stage {order} not reached.", 404)
    if task_key not in (definition.get("automated_tasks") or []):
        raise DomainError(
            VALIDATION_ERROR, f"Stage {order} has no task '{task_key}'.", 422
        )
    result = await engines.run_decision_engine(db, project, definition, instance)

    # §6.2: a stage starved of documents raises a Missing Information report
    if result["evaluation"]["waiting_on"] and definition["key"] == "requirements_collection":
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
    definition = await _definition(principal, order)
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
    """§9 + acceptance #9.

    Two separate rules:
      * the caller must hold the stage's approver_role, and
      * a `client` position is only exercised through scoped client-portal
        access — a full-module user must not stand in for the client.
    """
    db = principal.tenant_db
    approver_role = definition.get("approver_role") or ""
    role_name = principal.role.get("name", "")

    # A stage routed to the `client` position is signed off only through scoped
    # client-portal access. Keyed off the seeded `is_client_portal` role flag —
    # NOT the role name — so a full-module user can never stand in for the client
    # (acceptance #9), and renaming the client-contact role can't break it.
    if engines.is_client_approval(definition) and approver_role == "client":
        if not principal.role.get("is_client_portal"):
            raise DomainError(
                PERMISSION_DENIED,
                f"Stage '{definition['key']}' is a client approval; it can only be "
                "made through scoped client-portal access.",
                http_status=403,
            )

    allowed = await engines.may_approve(
        db, approver_role, str(principal.user["_id"]), role_name
    )
    if not allowed:
        raise DomainError(
            PERMISSION_DENIED,
            f"Approving this stage requires the '{approver_role}' position.",
            http_status=403,
        )


async def approve_stage(
    principal: ClientPrincipal, project_id: str, order: int, comment: str | None
) -> dict:
    """§5.4 — approved → stage approved, project moves to the next stage."""
    project = await _project(principal, project_id)
    definition = await _definition(principal, order)
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

    # §1: run the stage's integrations while it is STILL awaiting the decision.
    # A failing integration (e.g. Inventory's INSUFFICIENT_STOCK at Stage 8)
    # raises here, leaving the stage `pending_approval` and recoverable — never
    # a stage marked `approved` whose side effects never happened.
    integration = await _run_integrations(principal, project, definition)

    approval = await repo.open_approval(db, instance["_id"])
    if approval is not None:
        await db[repo.APPROVALS].update_one(
            {"_id": approval["_id"]},
            {"$set": {"state": "approved", "decision": {
                "by": str(principal.user["_id"]), "at": _now(), "comment": comment,
            }}},
        )
    await repo.set_stage_fields(db, instance["_id"], {"status": "approved"})

    history = list(project.get("stage_history") or [])
    history.append({
        "order": order, "key": definition["key"],
        "entered_at": instance.get("entered_at"), "exited_at": _now(),
        "result": "approved",
    })
    await _log(principal, "stage.approved",
               {"type": "project", "id": project_id, "label": project["name"]},
               {"stage": definition["key"], "order": order, "comment": comment})

    fields: dict[str, Any] = {"stage_history": history}
    if order >= LAST_STAGE_ORDER:
        fields.update({"status": "completed", "completed_at": _now()})
        await repo.update(db, repo.PROJECTS, project["_id"], fields)
        await _log(principal, "project.completed",
                   {"type": "project", "id": project_id, "label": project["name"]},
                   {"code": project["code"]})
        return {
            "stage": "approved", "project_status": "completed",
            "handover": integration.get("handover"), "next_stage": None,
        }

    next_def = await _definition(principal, order + 1)
    fields.update({
        "current_stage_order": next_def["order"],
        "current_stage_key": next_def["key"],
    })
    updated = await repo.update(db, repo.PROJECTS, project["_id"], fields)
    assert updated is not None
    next_instance = await _enter_stage(principal, updated, next_def)
    return {
        "stage": "approved", "project_status": updated["status"],
        "integration": integration,
        "next_stage": {"order": next_def["order"], "key": next_def["key"],
                       "status": next_instance["status"]},
    }


async def reject_stage(
    principal: ClientPrincipal, project_id: str, order: int,
    comment: str, report_type: str | None, owner_id: str | None,
) -> dict:
    """§5.5 — generate the typed report, assign an owner, increment
    recovery_loops, reopen the stage (acceptance #5)."""
    project = await _project(principal, project_id)
    definition = await _definition(principal, order)
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
    # the rejection reopens the stage; the recovery block may hold it instead
    hold = recovery.get("state") == "on_hold"
    await repo.set_stage_fields(db, instance["_id"], {
        "status": "on_hold" if hold else "rejected",
        "blocking_reason": comment,
    })
    if hold:
        await repo.update(db, repo.PROJECTS, project["_id"], {"status": "on_hold"})
    else:
        instance = await repo.stage_instance(db, project["_id"], order)
        assert instance is not None
        await repo.set_stage_fields(db, instance["_id"], {"status": "in_progress"})
        instance = await repo.stage_instance(db, project["_id"], order)
        assert instance is not None
        await engines.run_decision_engine(db, project, definition, instance)

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
    if key == "material_procurement":
        return {"reservations": await _reserve_stock(principal, project)}
    if key == "client_handover":
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
    bom = await db[repo.DELIVERABLES].find_one({
        "project_id": project["_id"], "kind": "bom", "is_deleted": {"$ne": True},
    })
    if bom is None:
        return []
    lines = (bom.get("lines") or [])
    if not lines:
        return []

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
    pack: list[dict] = []
    for kind, title in (
        ("certificate", "Completion Certificate"),
        ("certificate", "Warranty"),
        ("report", "Operation & Maintenance Manuals"),
        ("shop_drawing", "As-built Drawings"),
    ):
        doc = await repo.insert(db, repo.DELIVERABLES, {
            "project_id": project["_id"],
            "stage_key": "client_handover",
            "kind": kind,
            "title": title,
            "current_version": 1,
            "versions": [{"v": 1, "file_ref": f"generated:{project['code']}:{title}",
                          "author_id": actor, "at": _now(), "note": "handover pack"}],
            "classification": "auto",
            "ocr_text": None,
            "immutable_audit": [{"action": "created", "by": actor, "at": _now()}],
            "created_by": actor,
        })
        pack.append({"id": str(doc["_id"]), "kind": kind, "title": title})

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
               {"documents": len(pack), "final_invoice": bool(invoice)})
    return {"documents": pack, "final_invoice": invoice}


# --- deliverables (§3.7) -----------------------------------------------------

async def list_deliverables(
    principal: ClientPrincipal, project_id: str, kind: str | None,
    skip: int, limit: int,
) -> tuple[list[dict], int]:
    project = await _project(principal, project_id)
    query: dict[str, Any] = {"project_id": project["_id"]}
    if kind:
        query["kind"] = kind
    return await repo.list_docs(
        principal.tenant_db, repo.DELIVERABLES, query, skip, limit
    )


async def create_deliverable(
    principal: ClientPrincipal, project_id: str, payload: DeliverableCreate
) -> dict:
    project = await _project(principal, project_id)
    actor = str(principal.user["_id"])
    doc = await repo.insert(principal.tenant_db, repo.DELIVERABLES, {
        "project_id": project["_id"],
        "stage_key": payload.stage_key or project["current_stage_key"],
        "kind": payload.kind,
        "title": payload.title,
        "current_version": 1,
        "versions": [{"v": 1, "file_ref": payload.file_ref, "author_id": actor,
                      "at": _now(), "note": payload.note or "initial"}],
        "classification": payload.classification,
        "ocr_text": payload.ocr_text,
        "lines": [line.model_dump() for line in payload.lines],
        "immutable_audit": [{"action": "created", "by": actor, "at": _now()}],
        "created_by": actor,
    })
    await _log(principal, "deliverable.created",
               {"type": "deliverable", "id": str(doc["_id"]), "label": doc["title"]},
               {"project": project["code"], "kind": payload.kind})
    return doc


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
    await db[repo.DELIVERABLES].update_one(
        {"_id": oid},
        {
            "$push": {
                "versions": {"v": next_v, "file_ref": payload.file_ref,
                             "author_id": actor, "at": _now(),
                             "note": payload.note or f"revision {next_v}"},
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
    return updated


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
    project = await _project(principal, project_id)
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
    """§4: on_hold suspends the project until the recovery report is resolved."""
    if project.get("status") != "on_hold":
        return
    db = principal.tenant_db
    still_open = await repo.open_reports(db, project["_id"], OPEN_REPORT_STATUSES)
    if still_open:
        return
    await repo.update(db, repo.PROJECTS, project["_id"], {"status": "active"})
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
    project = await _project(principal, project_id)
    return await repo.list_docs(
        principal.tenant_db, repo.JOB_COSTS, {"project_id": project["_id"]},
        skip, limit,
    )


# --- config (§12) ------------------------------------------------------------

async def list_stage_config(principal: ClientPrincipal) -> list[dict]:
    return await repo.stage_defs(principal.tenant_db)


async def patch_stage_config(
    principal: ClientPrincipal, key: str, patch: StageConfigPatch
) -> dict:
    db = principal.tenant_db
    definition = await repo.stage_def_by_key(db, key)
    if definition is None:
        raise DomainError(TENANT_NOT_FOUND, f"Stage '{key}' is not defined.", 404)
    fields = {k: v for k, v in patch.model_dump(exclude_unset=True).items() if v is not None}
    if not fields:
        return definition
    await db[repo.STAGE_DEFS].update_one({"key": key}, {"$set": fields})
    updated = await repo.stage_def_by_key(db, key)
    assert updated is not None
    await _log(principal, "projects.stage_config_updated",
               {"type": "stage_definition", "id": key, "label": updated["name"]},
               {"fields": list(fields)})
    return updated


async def list_gate_config(principal: ClientPrincipal) -> list[dict]:
    return await repo.gate_rules(principal.tenant_db)


async def patch_gate_config(
    principal: ClientPrincipal, key: str, patch: GateConfigPatch
) -> dict:
    """§8: thresholds are seeded defaults, editable per tenant."""
    db = principal.tenant_db
    rule = await repo.gate_rule(db, key)
    if rule is None:
        raise DomainError(TENANT_NOT_FOUND, f"Gate '{key}' is not defined.", 404)
    fields = {k: v for k, v in patch.model_dump(exclude_unset=True).items() if v is not None}
    if not fields:
        return rule
    await db[repo.GATE_RULES].update_one({"key": key}, {"$set": fields})
    updated = await repo.gate_rule(db, key)
    assert updated is not None
    await _log(principal, "projects.gate_config_updated",
               {"type": "gate_rule", "id": key, "label": key},
               {"fields": list(fields)})
    return updated


async def list_approver_config(principal: ClientPrincipal) -> list[dict]:
    return await repo.approver_map(principal.tenant_db)
