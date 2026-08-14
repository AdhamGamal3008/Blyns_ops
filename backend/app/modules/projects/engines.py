"""The two engines that drive the stage machine
(docs/modules/PROJECT_MANAGEMENT.md §5 Universal Approval, §6 Automated
Decision).

Both are deterministic and idempotent (§6): they recompute state from the
current documents, dependencies and gate results, so re-running is always safe.
Nothing here advances a stage on its own — advancement needs blocking gates
passed, automated validation passed, AND an approver holding the stage's role
(§15 acceptance #1).
"""

from __future__ import annotations

from datetime import UTC, datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.modules.projects import repository as repo
from app.modules.projects.permissions import HANDOVER_STAGE_KEY


def _now() -> datetime:
    return datetime.now(UTC)


# --- gate evaluation (§8 physical gates) -------------------------------------

def evaluate_measurement(rule: dict, readings: list[dict]) -> tuple[bool, bool, str]:
    """Score a measurement gate against its seeded threshold.

    Returns (passed, severe, explanation). `severe` marks a breach of the rule's
    `severe_threshold` — Stage 7's severe deviation is what drives the project
    to on_hold rather than a normal recovery loop (§8, acceptance #3).
    """
    threshold = rule.get("threshold") or {}
    values = [float(r["value"]) for r in readings if r.get("value") is not None]
    if not values:
        return False, False, "No readings captured."

    # site_defined thresholds are configured per project; nothing to compare to,
    # so the presence of a log is the gate (§8 ambient_rh_temp_log).
    if threshold.get("site_defined"):
        return True, False, "Site-defined window; log captured."

    worst = max(values)
    lowest = min(values)

    # min/max window — e.g. timber moisture content 6–9%
    if "min" in threshold or "max" in threshold:
        lo = float(threshold.get("min", float("-inf")))
        hi = float(threshold.get("max", float("inf")))
        passed = lowest >= lo and worst <= hi
        unit = threshold.get("unit", "")
        return (
            passed, False,
            f"Readings {lowest}–{worst}{unit} against window {lo}–{hi}{unit}.",
        )

    # single upper bound, possibly with a severe tier
    for field in ("max_deviation_mm", "max_rh_pct", "max_deviation_in"):
        if field in threshold:
            limit = float(threshold[field])
            severe_limit = float((rule.get("severe_threshold") or {}).get(field, float("inf")))
            passed = worst <= limit
            severe = worst > severe_limit
            return (
                passed, severe,
                f"Worst reading {worst} against limit {limit}"
                + (f" (severe beyond {severe_limit})" if severe else "") + ".",
            )

    # target ± tolerance — e.g. the standardized 3mm reveal
    if "target_mm" in threshold:
        target = float(threshold["target_mm"])
        tol = float(threshold.get("tolerance_mm", 0))
        passed = all(abs(v - target) <= tol for v in values)
        return passed, False, f"Readings against {target}±{tol}mm."

    return True, False, "No comparable threshold configured."


def evaluate_inspection(rule: dict, results: list[dict]) -> tuple[bool, bool, str]:
    """A checklist gate passes only when every item is marked passed (§8)."""
    checklist: list[str] = [str(c) for c in (rule.get("checklist") or [])]
    # a result with no `item` names nothing and cannot answer the checklist
    marked: dict[str, bool] = {
        str(r["item"]): bool(r.get("passed"))
        for r in results if r.get("item") is not None
    }
    missing = [item for item in checklist if item not in marked]
    if missing:
        return False, False, f"Checklist incomplete: {len(missing)} item(s) unanswered."
    failed = [item for item, ok in marked.items() if not ok]
    if failed:
        return False, False, f"Checklist failed: {'; '.join(failed)}."
    return True, False, "All checklist items passed."


def evaluate_gate_result(rule: dict, payload: dict) -> tuple[bool, bool, str]:
    if rule.get("type") == "inspection":
        return evaluate_inspection(rule, payload.get("checklist_results") or [])
    return evaluate_measurement(rule, payload.get("readings") or [])


# --- the Automated Decision Engine (§6) --------------------------------------

async def evaluate_stage(
    db: AsyncIOMotorDatabase, project: dict, definition: dict, instance: dict
) -> dict:
    """Recompute a stage's gate/task picture from current state.

    §6's rigid path: document check → dependency check → automated validation.
    Pure — it reports, it does not write. `run_decision_engine` applies it.
    """
    supplied: set[str] = set(instance.get("documents_supplied") or [])
    # Dependencies vary by workflow_type; a caller may hand us another template's
    # copy of this stage (same key/order), so evaluate against the project's own
    # template (docs/CONCURRENT_WORKFLOW_PLAN.md).
    workflow_type = project.get("workflow_type", "sequential")
    if definition.get("workflow_type") != workflow_type:
        own = await repo.stage_def_by_key(db, definition["key"], workflow_type)
        if own is not None:
            definition = own
    entry_gates = definition.get("entry_gates") or []
    quality_gates = definition.get("quality_gates") or []

    # 2. document check
    waiting_on: list[str] = []
    for gate in entry_gates:
        if gate.get("type") != "document":
            continue
        if gate.get("blocking") and gate["key"] not in supplied:
            waiting_on.append(f"doc:{gate['key']}")

    # 3. dependency check — a preceding stage that is not approved blocks this one
    blocked_by: list[str] = []
    for gate in entry_gates:
        if gate.get("type") != "dependency" or not gate.get("blocking"):
            continue
        depends_on = gate.get("depends_on")
        dep_def = await repo.stage_def_by_key(db, depends_on) if depends_on else None
        if dep_def is None:
            # a phase reference (e.g. acclimation) rather than a stage: it is
            # satisfied by supplying its document/gate evidence
            if gate["key"] not in supplied:
                waiting_on.append(f"phase:{depends_on}")
            continue
        dep_instance = await repo.stage_instance(db, project["_id"], dep_def["order"])
        if dep_instance is None or dep_instance.get("status") != "approved":
            blocked_by.append(f"stage:{dep_def['order']}:{dep_def['key']}")

    # Gating is the declared dependencies above — the sequential template encodes
    # the linear chain (each stage depends on the one before), the concurrent one a
    # DAG (2-8 depend on 1, 9 on all). No hard-coded "every lower order approved"
    # rule, which is what let stages run in parallel (docs/CONCURRENT_WORKFLOW_PLAN.md).

    # 4. automated validation — blocking quality gates must have a passing result
    gate_failures: list[dict] = []
    severe = False
    for gate_key in quality_gates:
        rule = await repo.gate_rule(db, gate_key)
        if rule is None or not rule.get("blocking", True):
            continue
        result = await repo.latest_gate_result(db, instance["_id"], gate_key)
        if result is None:
            gate_failures.append({"gate_key": gate_key, "reason": "No result captured."})
        elif not result.get("passed"):
            gate_failures.append({
                "gate_key": gate_key,
                "reason": result.get("explanation") or "Gate failed.",
            })
            if result.get("severe"):
                severe = True

    return {
        "waiting_on": waiting_on,
        "blocked_by": blocked_by,
        "gate_failures": gate_failures,
        "severe": severe,
        "ready": not waiting_on and not blocked_by and not gate_failures,
    }


def next_status(evaluation: dict, current: str) -> str:
    """§4: the state a stage should sit in given its evaluation.

    on_hold is sticky — only resolving the recovery report clears it (§4).
    """
    if current == "on_hold":
        return "on_hold"
    if evaluation["severe"]:
        return "on_hold"
    if evaluation["blocked_by"]:
        return "blocked"
    if evaluation["waiting_on"]:
        return "waiting"
    return "in_progress"


async def run_decision_engine(
    db: AsyncIOMotorDatabase, project: dict, definition: dict, instance: dict
) -> dict:
    """Apply §6 to a stage instance and persist the resulting state.

    Idempotent: it derives everything from current documents/dependencies/gate
    results, so calling it twice lands in the same place.
    """
    evaluation = await evaluate_stage(db, project, definition, instance)
    status = next_status(evaluation, instance.get("status", "pending"))

    task_results = [
        {"task": task, "status": "done" if evaluation["ready"] else "waiting"}
        for task in (definition.get("automated_tasks") or [])
    ]
    blocking_reason = None
    if evaluation["blocked_by"]:
        blocking_reason = f"Blocked by {', '.join(evaluation['blocked_by'])}"
    elif evaluation["waiting_on"]:
        blocking_reason = f"Waiting on {', '.join(evaluation['waiting_on'])}"
    elif evaluation["gate_failures"]:
        blocking_reason = "; ".join(
            f"{f['gate_key']}: {f['reason']}" for f in evaluation["gate_failures"]
        )

    updated = await repo.set_stage_fields(db, instance["_id"], {
        "status": status,
        "waiting_on": evaluation["waiting_on"],
        "blocked_by": evaluation["blocked_by"],
        "task_results": task_results,
        "blocking_reason": blocking_reason,
        "last_evaluated_at": _now(),
    })
    assert updated is not None
    return {"instance": updated, "evaluation": evaluation}


# --- the Universal Approval Engine (§5) --------------------------------------

async def resolve_approvers(
    db: AsyncIOMotorDatabase, approver_role: str
) -> tuple[list[str], list[str]]:
    """§9: a position resolves to tenant client roles and/or specific users
    through the Settings-editable approver map."""
    entry = await repo.approver_entry(db, approver_role)
    if entry is None:
        return [], []
    roles = [r.lower() for r in (entry.get("client_roles") or [])]
    users = [str(u) for u in (entry.get("assigned_user_ids") or [])]
    return roles, users


async def holds_position(
    db: AsyncIOMotorDatabase, approver_role: str, user_id: str, role_name: str
) -> bool:
    """§9: the caller natively holds the position — an explicit user assignment
    or a client role the position maps to. Excludes delegation, so it is the
    right check for granting a delegation (a deputy cannot re-delegate)."""
    roles, users = await resolve_approvers(db, approver_role)
    if user_id in users:
        return True
    return role_name.lower() in roles


async def may_approve(
    db: AsyncIOMotorDatabase, approver_role: str, user_id: str, role_name: str
) -> bool:
    """§9 + SOP §2: the caller may approve if they natively hold the position OR
    a named deputy holds an active written delegation of it."""
    if await holds_position(db, approver_role, user_id, role_name):
        return True
    return await repo.has_active_delegation(db, approver_role, user_id)


async def run_auto_validation(
    db: AsyncIOMotorDatabase, project: dict, definition: dict, instance: dict
) -> dict:
    """§5.2 — system checks constraints, budgets and that all blocking gates
    passed. A failure short-circuits back to in_progress with a report."""
    evaluation = await evaluate_stage(db, project, definition, instance)
    checks: list[dict] = [
        {
            "key": "documents_present",
            "passed": not evaluation["waiting_on"],
            "detail": ", ".join(evaluation["waiting_on"]) or "All required documents supplied.",
        },
        {
            "key": "dependencies_complete",
            "passed": not evaluation["blocked_by"],
            "detail": ", ".join(evaluation["blocked_by"]) or "All preceding stages approved.",
        },
        {
            "key": "quality_gates_passed",
            "passed": not evaluation["gate_failures"],
            "detail": "; ".join(
                f"{f['gate_key']}: {f['reason']}" for f in evaluation["gate_failures"]
            ) or "All blocking quality gates passed.",
        },
    ]

    # budget check — a stage may not be approved with the project over its
    # planned budget unless there is no budget set
    budget = project.get("budget") or {}
    planned = float(budget.get("planned") or 0)
    actual = float(budget.get("actual") or 0)
    committed = float(budget.get("committed") or 0)
    over = planned > 0 and (actual + committed) > planned
    checks.append({
        "key": "budget_ok",
        "passed": not over,
        "detail": (
            f"Committed+actual {actual + committed:.2f} exceeds planned {planned:.2f}."
            if over else "Within planned budget."
        ),
    })

    # v2.0 Stage 6 · Factory Release (§5-C): the four v1.0 approvals became one
    # release decision — all four checklist sections must be complete first.
    checklist = definition.get("release_checklist") or []
    if checklist:
        done = set(instance.get("checklist_done") or [])
        missing = [s for s in checklist if s not in done]
        checks.append({
            "key": "release_checklist_complete",
            "passed": not missing,
            "detail": (
                "Release checklist incomplete: " + ", ".join(missing)
                if missing else "All release checklist sections complete."
            ),
        })

    # v2.0 Stage 9 · Handover (SOP §9): no open snag proceeds to handover unless
    # a written client acceptance is on record.
    if definition.get("key") == HANDOVER_STAGE_KEY:
        snags = await repo.open_snags(db, project["_id"])
        accepted = bool(project.get("client_acceptance"))
        checks.append({
            "key": "snags_closed",
            "passed": not snags or accepted,
            "detail": (
                "All snags closed." if not snags
                else "Open snags waived by written client acceptance."
                if accepted
                else f"{len(snags)} open snag(s) — close them or record client acceptance."
            ),
        })

    return {
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
        "evaluation": evaluation,
    }


async def open_or_create_approval(
    db: AsyncIOMotorDatabase, project: dict, definition: dict,
    instance: dict, actor_id: str,
) -> dict:
    existing = await repo.open_approval(db, instance["_id"])
    if existing is not None:
        return existing
    approver_role = definition.get("approver_role")
    _, users = await resolve_approvers(db, approver_role or "")
    return await repo.insert(db, repo.APPROVALS, {
        "stage_instance_id": instance["_id"],
        "project_id": project["_id"],
        "approver_role": approver_role,
        "co_approver_roles": definition.get("co_approver_roles") or [],
        "assigned_to": users[0] if len(users) == 1 else None,
        "state": "draft",
        "auto_validation": None,
        "decision": None,
        "change_report_id": None,
        "created_by": actor_id,
    })


async def bump_recovery(db: AsyncIOMotorDatabase, instance_id: ObjectId) -> int:
    """§5.5 — a rejection increments the mandatory resubmission counter."""
    doc = await db[repo.STAGE_INSTANCES].find_one_and_update(
        {"_id": instance_id}, {"$inc": {"recovery_loops": 1}}, return_document=True,
    )
    return int(doc.get("recovery_loops", 0)) if doc else 0
