"""Production module service layer (docs/PRODUCTION_MODULE_PLAN.md).

Phase 1: the Work Order object + the cross-project Queue.
- `propose_work_orders` reads a project's BOM (line-carrying, never the shadow
  file) + its newest shop drawing, and proposes one draft WO per BOM line, pinned
  to that drawing's current revision (§2.1). Nothing is persisted.
- `create_work_orders` is the manager's confirm step (D4): it requires the
  `production_manager` position and commits the reviewed drafts.
- The status model, QC hold, Inventory consume, Finance job costs, and the Stage-6
  checklist drive all land in Phase 2.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bson import ObjectId

from app.core.audit import write_activity
from app.core.errors import (
    NOT_FOUND,
    PERMISSION_DENIED,
    VALIDATION_ERROR,
    DomainError,
)
from app.modules.production import repository as repo
from app.modules.production.models import (
    QCResultInput,
    RequestQCInput,
    ReworkInput,
    ShortfallInput,
    WorkOrderConfirm,
)
from app.modules.production.permissions import (
    ACTIVE_AT_STATION,
    ALLOWED_TRANSITIONS,
    DONE_STATUSES,
    DRIVEN_SECTIONS,
    FACTORY_RELEASE_KEY,
    MATERIAL_PROCUREMENT_KEY,
    PHASE_CLEARED,
    QUEUE_DEFAULT_DAYS,
)
from app.modules.projects import engines as pm_engines
from app.modules.projects import repository as pm_repo
from app.tenant.deps import ClientPrincipal


def _now() -> datetime:
    return datetime.now(UTC)


def _oid(value: str, what: str) -> ObjectId:
    try:
        return ObjectId(value)
    except Exception as exc:
        raise DomainError(NOT_FOUND, f"{what} not found.", 404) from exc


async def _log(
    principal: ClientPrincipal, action: str, entity: dict, details: dict | None = None
) -> None:
    await write_activity(
        principal.tenant_db,
        actor_id=str(principal.user["_id"]),
        action=action,
        entity=entity,
        details=details or {},
        actor_name=principal.user["name"],
        module="production",
    )


async def _require_manager(principal: ClientPrincipal) -> None:
    """The `production_manager` position — the pipeline already owns it (Stage 6).
    Plain `production` WRITE is not enough to commit WOs (D4)."""
    ok = await pm_engines.may_approve(
        principal.tenant_db, "production_manager",
        str(principal.user["_id"]), principal.role.get("name", ""),
    )
    if not ok:
        raise DomainError(
            PERMISSION_DENIED,
            "Confirming work orders requires the 'production_manager' position.",
            http_status=403,
        )


# --- stations ----------------------------------------------------------------

async def list_stations(principal: ClientPrincipal) -> list[dict]:
    """Work centres enriched with their current load vs daily capacity (§3).
    Load balancing is only meaningful once there are WOs — it reads real data,
    never a projected empty board."""
    db = principal.tenant_db
    stations = await repo.list_stations(db)
    load = await repo.station_load(db, list(ACTIVE_AT_STATION))
    for s in stations:
        info = load.get(str(s["_id"]), {"units": 0.0, "count": 0})
        cap = float(s.get("capacity_units_per_day") or 0)
        units = float(info["units"])
        s["load"] = {
            "units": round(units, 2),
            "work_orders": int(info["count"]),
            "capacity": cap,
            "utilization": round(100 * units / cap) if cap else None,
        }
    return stations


async def context(principal: ClientPrincipal) -> dict:
    """What the caller may do in Production — drives the UI's manager-only
    affordances without leaking the projects approver map."""
    can_manage = await pm_engines.may_approve(
        principal.tenant_db, "production_manager",
        str(principal.user["_id"]), principal.role.get("name", ""),
    )
    return {"can_manage": can_manage}


# --- generation (D4: auto-propose, manager confirms) -------------------------

def _station_matches(station: dict, category: str | None) -> bool:
    if not category:
        return False
    cat = category.lower()
    return any(
        mt.lower() in cat or cat in mt.lower()
        for mt in station.get("material_types") or []
    )


def _suggest_station(stations: list[dict], category: str | None) -> str | None:
    """Best-effort entry station from the product category ↔ a station's material
    types (used at generation). Phase 3 auto-allocation refines this by load."""
    return next(
        (str(s["_id"]) for s in stations if _station_matches(s, category)), None
    )


async def propose_work_orders(
    principal: ClientPrincipal, project_id: str
) -> list[dict]:
    db = principal.tenant_db
    project = await repo.get_project(db, _oid(project_id, "Project"))
    if project is None:
        raise DomainError(NOT_FOUND, "Project not found.", 404)

    bom = await repo.reservable_bom(db, project["_id"])
    if bom is None:
        raise DomainError(
            VALIDATION_ERROR,
            "This project has no BOM with line items to generate work orders from.",
            422,
        )

    drawing = await repo.latest_shop_drawing(db, project["_id"])
    source_drawing = None
    if drawing is not None:
        source_drawing = {
            "deliverable_id": str(drawing["_id"]),
            "title": drawing.get("title"),
            "version": int(drawing.get("current_version", 1)),
        }

    stations = await repo.list_stations(db)
    due = (project.get("schedule") or {}).get("delivery_date")

    drafts: list[dict] = []
    for line in bom["lines"]:
        prod = None
        try:
            prod = await repo.product(db, ObjectId(str(line["product_id"])))
        except Exception:
            prod = None
        prod = prod or {}
        sku = prod.get("sku")
        name = prod.get("name") or prod.get("description")
        drafts.append({
            "project_id": str(project["_id"]),
            "item_name": name or sku or "Manufactured item",
            "source_drawing": source_drawing,
            "bom_lines": [{
                "product_id": str(line["product_id"]),
                "sku": sku,
                "description": name,
                "qty": float(line["qty"]),
                "uom": prod.get("unit"),
            }],
            "qty_ordered": float(line["qty"]),
            "station_id": _suggest_station(stations, prod.get("category")),
            "due_date": due,
        })
    return drafts


def _wo_code(project: dict, seq: int) -> str:
    code = str(project.get("code") or "")
    num = code.rsplit("-", 1)[-1] if "-" in code else code  # PRJ-0001 → 0001
    return f"WO-{num}-{seq:02d}"


async def create_work_orders(
    principal: ClientPrincipal, payload: WorkOrderConfirm
) -> list[dict]:
    await _require_manager(principal)
    db = principal.tenant_db
    actor = str(principal.user["_id"])

    projects: dict[str, dict] = {}
    created: list[dict] = []
    for item in payload.work_orders:
        project = projects.get(item.project_id)
        if project is None:
            project = await repo.get_project(db, _oid(item.project_id, "Project"))
            if project is None:
                raise DomainError(NOT_FOUND, "Project not found.", 404)
            projects[item.project_id] = project

        seq = await repo.next_wo_seq(db, project["_id"])
        code = _wo_code(project, seq)
        station_id = item.station_id
        doc = await repo.insert_work_order(db, {
            "code": code,
            "project_id": project["_id"],
            "project_code": project.get("code"),
            "crm_account_id": project.get("crm_account_id"),
            "client_name": await repo.account_name(db, project.get("crm_account_id")),
            "item_name": item.item_name,
            "source_drawing": item.source_drawing.model_dump() if item.source_drawing else None,
            "bom_lines": [line.model_dump() for line in item.bom_lines],
            "qty": {"ordered": item.qty_ordered, "done": 0.0},
            "station_route": [station_id] if station_id else [],
            "current_station_id": station_id,
            "assigned_function": None,
            "assigned_user_id": None,
            "due_date": item.due_date,
            "status": "queued",
            "blocked_by": None,
            "subcontract": None,
            "history": [{
                "at": _now(), "by": actor,
                "from_status": None, "to_status": "queued", "note": "created",
            }],
            "created_by": actor,
            "updated_by": actor,
        })
        created.append(doc)
        await _log(
            principal, "production.wo_created",
            {"type": "work_order", "id": str(doc["_id"]), "label": code},
            {"project": project.get("code"), "qty": item.qty_ordered},
        )
    return created


# --- read surfaces (Queue, register, detail) ---------------------------------

async def _enrich(db, docs: list[dict]) -> None:
    """Attach the derived station name + the revision-conflict flag (plan §2.1),
    computed on read so a superseded drawing surfaces without a stored stale bit."""
    if not docs:
        return
    stations = await repo.stations_map(db)
    draw_ids = [
        ObjectId(d["source_drawing"]["deliverable_id"])
        for d in docs if d.get("source_drawing")
    ]
    versions = await repo.deliverable_versions(db, draw_ids) if draw_ids else {}
    for d in docs:
        station = stations.get(d.get("current_station_id") or "")
        d["station_name"] = station["name"] if station else None
        sd = d.get("source_drawing")
        d["revision_conflict"] = bool(
            sd and versions.get(sd["deliverable_id"], sd["version"]) > sd["version"]
        )


async def list_work_orders(
    principal: ClientPrincipal, project_id: str | None, status: str | None,
    station_id: str | None, skip: int, limit: int,
) -> tuple[list[dict], int]:
    db = principal.tenant_db
    query: dict = {}
    if project_id:
        query["project_id"] = _oid(project_id, "Project")
    if status:
        query["status"] = status
    if station_id:
        query["current_station_id"] = station_id
    docs, total = await repo.list_work_orders(db, query, skip, limit)
    await _enrich(db, docs)
    return docs, total


async def get_work_order(principal: ClientPrincipal, wo_id: str) -> dict:
    db = principal.tenant_db
    doc = await repo.get_work_order(db, _oid(wo_id, "Work order"))
    if doc is None:
        raise DomainError(NOT_FOUND, "Work order not found.", 404)
    await _enrich(db, [doc])
    return doc


async def queue(
    principal: ClientPrincipal, station_id: str | None, project_id: str | None,
    due_days: int, all_due: bool,
) -> list[dict]:
    db = principal.tenant_db
    query: dict = {"status": {"$nin": list(DONE_STATUSES)}}
    if station_id:
        query["current_station_id"] = station_id
    if project_id:
        query["project_id"] = _oid(project_id, "Project")
    if not all_due:
        horizon = _now() + timedelta(days=due_days or QUEUE_DEFAULT_DAYS)
        # a null due date has no deadline — still live work, kept in the list
        query["$or"] = [{"due_date": None}, {"due_date": {"$lte": horizon}}]

    docs = await repo.queue_work_orders(db, query)
    await _enrich(db, docs)
    # due-date ascending, but null (no deadline) sorts last, not first. Normalise
    # to naive so a mix of tz-aware/naive Mongo datetimes stays comparable.
    def _due_key(w: dict) -> datetime:
        d = w.get("due_date")
        return d.replace(tzinfo=None) if isinstance(d, datetime) else datetime.max
    docs.sort(key=_due_key)
    return docs


# --- Phase 2: status transitions (§2.2) --------------------------------------


async def _wo_or_404(db, wo_id: str) -> dict:
    wo = await repo.get_work_order(db, _oid(wo_id, "Work order"))
    if wo is None:
        raise DomainError(NOT_FOUND, "Work order not found.", 404)
    return wo


async def _project_of(db, wo: dict) -> dict:
    project = await repo.get_project(db, wo["project_id"])
    if project is None:
        raise DomainError(NOT_FOUND, "Project not found.", 404)
    return project


def _assert_transition(wo: dict, to: str) -> None:
    if to not in ALLOWED_TRANSITIONS.get(wo["status"], set()):
        raise DomainError(
            VALIDATION_ERROR, f"A {wo['status']} work order cannot move to {to}.", 422,
        )


async def _set_status(
    db, wo: dict, to: str, actor: str, note: str | None = None, **extra
) -> dict:
    entry = {"at": _now(), "by": actor, "from_status": wo["status"],
             "to_status": to, "note": note}
    updated = await repo.update_work_order(db, wo["_id"], {
        "status": to, "updated_by": actor,
        "history": [*(wo.get("history") or []), entry], **extra,
    })
    assert updated is not None
    return updated


async def _assert_materials_reserved(db, project: dict) -> None:
    """Sync rule 1: a WO cannot be released before Stage 5 is approved."""
    sdef = await pm_repo.stage_def_by_key(db, MATERIAL_PROCUREMENT_KEY)
    order = int(sdef["order"]) if sdef else 5
    inst = await pm_repo.stage_instance(db, project["_id"], order)
    if inst is None or inst.get("status") != "approved":
        raise DomainError(
            VALIDATION_ERROR,
            "Materials are not reserved yet — Stage 5 (Material Procurement) must "
            "be approved before a work order can be released.",
            422,
        )


async def _post_job_cost(principal: ClientPrincipal, project_id: str, payload) -> None:
    """Post a job cost through the projects service (Dr COGS / Cr AP + budget
    roll-up). If Finance is unavailable, still capture the actual on the budget."""
    from app.modules.projects import service as pm_service
    try:
        await pm_service.create_job_cost(principal, project_id, payload)
    except DomainError as exc:
        if exc.http_status != 409:
            raise
        payload.post_to_finance = False
        await pm_service.create_job_cost(principal, project_id, payload)


async def _material_value(db, wo: dict) -> float:
    total = 0.0
    for line in wo.get("bom_lines") or []:
        try:
            prod = await repo.product(db, ObjectId(str(line["product_id"])))
        except Exception:
            prod = None
        total += float((prod or {}).get("cost_price") or 0) * float(line["qty"])
    return round(total, 2)


async def _book_material_cost(principal: ClientPrincipal, project: dict, wo: dict) -> None:
    """Issue the WO's material from the reservation → a material actual that draws
    the Stage-5 commitment down (a reserved-then-consumed line counts once)."""
    from app.modules.projects.models import JobCostCreate
    value = await _material_value(principal.tenant_db, wo)
    if value <= 0:
        return
    await _post_job_cost(principal, str(project["_id"]), JobCostCreate(
        cost_type="material", stage_key=FACTORY_RELEASE_KEY,
        description=f"{wo['code']} material", quantity=1, unit_cost=value,
    ))


async def _rework_material(principal: ClientPrincipal, project: dict, wo: dict) -> None:
    """D1: a rework draws a NEW Inventory reservation (extra material physically
    leaves stock) and books it as a second material actual — material consumed
    twice is recorded twice, never written off silently."""
    from app.modules.inventory import service as inv_service
    from app.modules.inventory.models import MovementCreate
    from app.modules.projects.models import JobCostCreate

    db = principal.tenant_db
    warehouse = await repo.default_warehouse(db)
    value = 0.0
    for line in wo.get("bom_lines") or []:
        pid = str(line["product_id"])
        try:
            prod = await repo.product(db, ObjectId(pid))
        except Exception:
            prod = None
        if warehouse is not None:
            await inv_service.create_movement(principal, MovementCreate(
                product_id=pid, warehouse_id=str(warehouse["_id"]), type="issue",
                qty=float(line["qty"]), note=f"Rework {wo['code']}",
                ref_module="production", ref_doc_id=str(wo["_id"]),
            ))
        value += float((prod or {}).get("cost_price") or 0) * float(line["qty"])
    value = round(value, 2)
    if value > 0:
        await _post_job_cost(principal, str(project["_id"]), JobCostCreate(
            cost_type="material", stage_key=FACTORY_RELEASE_KEY,
            description=f"{wo['code']} rework material", quantity=1, unit_cost=value,
        ))


async def _detail(db, wo: dict) -> dict:
    await _enrich(db, [wo])
    return wo


async def release_work_order(principal: ClientPrincipal, wo_id: str) -> dict:
    await _require_manager(principal)  # spec §7: production_manager releases WOs
    db = principal.tenant_db
    actor = str(principal.user["_id"])
    wo = await _wo_or_404(db, wo_id)
    _assert_transition(wo, "released")
    project = await _project_of(db, wo)
    await _assert_materials_reserved(db, project)
    wo = await _set_status(db, wo, "released", actor, blocked_by=None)
    await _log(principal, "production.wo_released",
               {"type": "work_order", "id": str(wo["_id"]), "label": wo["code"]}, {})
    await _recompute_pipeline(principal, project)
    return await _detail(db, wo)


async def start_work_order(principal: ClientPrincipal, wo_id: str) -> dict:
    db = principal.tenant_db
    actor = str(principal.user["_id"])
    wo = await _wo_or_404(db, wo_id)
    _assert_transition(wo, "in_progress")
    project = await _project_of(db, wo)
    first_start = wo["status"] == "released"
    wo = await _set_status(db, wo, "in_progress", actor, blocked_by=None)
    if first_start:
        await _book_material_cost(principal, project, wo)  # issue material from stock
    await _log(principal, "production.wo_started",
               {"type": "work_order", "id": str(wo["_id"]), "label": wo["code"]}, {})
    await _recompute_pipeline(principal, project)
    return await _detail(db, wo)


async def request_qc(
    principal: ClientPrincipal, wo_id: str, body: RequestQCInput
) -> dict:
    from app.modules.projects.models import JobCostCreate
    db = principal.tenant_db
    actor = str(principal.user["_id"])
    wo = await _wo_or_404(db, wo_id)
    _assert_transition(wo, "qc_pending")
    project = await _project_of(db, wo)
    qty = dict(wo.get("qty") or {})
    qty["done"] = body.qty_done if body.qty_done is not None else qty.get("ordered", 0)
    wo = await _set_status(db, wo, "qc_pending", actor, qty=qty)
    if body.labor_hours and body.labor_rate:
        await _post_job_cost(principal, str(project["_id"]), JobCostCreate(
            cost_type="labor", stage_key=FACTORY_RELEASE_KEY,
            description=f"{wo['code']} labor", hours=body.labor_hours,
            unit_cost=body.labor_rate,
        ))
    await _log(principal, "production.wo_qc_requested",
               {"type": "work_order", "id": str(wo["_id"]), "label": wo["code"]}, {})
    await _recompute_pipeline(principal, project)
    return await _detail(db, wo)


async def record_qc(
    principal: ClientPrincipal, wo_id: str, body: QCResultInput
) -> dict:
    db = principal.tenant_db
    actor = str(principal.user["_id"])
    wo = await _wo_or_404(db, wo_id)
    project = await _project_of(db, wo)
    if body.result == "pass":
        _assert_transition(wo, "passed")
        wo = await _set_status(db, wo, "passed", actor, blocked_by=None,
            qc={"result": "pass", "defects": [], "inspector_id": actor, "at": _now()})
        await _log(principal, "production.wo_qc_passed",
                   {"type": "work_order", "id": str(wo["_id"]), "label": wo["code"]}, {})
    else:
        _assert_transition(wo, "qc_hold")
        wo = await _set_status(db, wo, "qc_hold", actor,
            blocked_by={"type": "qc_hold", "note": body.note},
            qc={"result": "hold", "defects": body.defects, "note": body.note,
                "inspector_id": actor, "at": _now()})
        await _log(principal, "production.wo_qc_held",
                   {"type": "work_order", "id": str(wo["_id"]), "label": wo["code"]},
                   {"defects": len(body.defects)})
    await _recompute_pipeline(principal, project)
    return await _detail(db, wo)


async def rework_work_order(
    principal: ClientPrincipal, wo_id: str, body: ReworkInput
) -> dict:
    db = principal.tenant_db
    actor = str(principal.user["_id"])
    wo = await _wo_or_404(db, wo_id)
    _assert_transition(wo, "rework")
    project = await _project_of(db, wo)
    await _rework_material(principal, project, wo)  # D1: new reservation
    wo = await _set_status(db, wo, "rework", actor, note=body.note, blocked_by=None)
    await _log(principal, "production.wo_rework",
               {"type": "work_order", "id": str(wo["_id"]), "label": wo["code"]}, {})
    await _recompute_pipeline(principal, project)
    return await _detail(db, wo)


async def flag_shortfall(
    principal: ClientPrincipal, wo_id: str, body: ShortfallInput
) -> dict:
    db = principal.tenant_db
    actor = str(principal.user["_id"])
    wo = await _wo_or_404(db, wo_id)
    updated = await repo.update_work_order(db, wo["_id"], {
        "blocked_by": {"type": "material_shortfall", "note": body.note},
        "updated_by": actor,
    })
    assert updated is not None
    await _log(principal, "production.wo_shortfall",
               {"type": "work_order", "id": str(updated["_id"]), "label": updated["code"]},
               {"note": body.note})
    return await _detail(db, updated)


# --- pipeline drive (§2.3) ---------------------------------------------------


async def _recompute_pipeline(principal: ClientPrincipal, project: dict) -> None:
    """Roll WO progress up into the Stage-6 checklist + the display cache. A
    section flips to done only when EVERY live WO has cleared it; a regression
    (a QC hold routed to rework) reopens it. Projects with no WOs are left to
    manual marking (sync rule 4)."""
    db = principal.tenant_db
    wos = await repo.live_work_orders(db, project["_id"])
    if not wos:
        return
    n = len(wos)
    sections_pct = {
        sec: round(100 * sum(1 for w in wos if w["status"] in cleared) / n)
        for sec, cleared in PHASE_CLEARED.items()
    }
    await repo.upsert_rollup(db, project["_id"], sections_pct)

    sdef = await pm_repo.stage_def_by_key(db, FACTORY_RELEASE_KEY)
    if sdef is None:
        return
    inst = await pm_repo.stage_instance(db, project["_id"], int(sdef["order"]))
    if inst is None:
        return
    release_sections = sdef.get("release_checklist") or []
    done = set(inst.get("checklist_done") or [])
    before = set(done)
    for sec in DRIVEN_SECTIONS:
        if sec not in release_sections:
            continue
        if all(w["status"] in PHASE_CLEARED[sec] for w in wos):
            done.add(sec)
        else:
            done.discard(sec)
    if done != before:
        await pm_repo.set_stage_fields(db, inst["_id"], {"checklist_done": sorted(done)})
        await _log(principal, "production.pipeline_synced",
                   {"type": "project", "id": str(project["_id"]), "label": project.get("name")},
                   {"checklist_done": sorted(done)})


async def project_rollup(principal: ClientPrincipal, project_id: str) -> dict:
    """The read-only pipeline mirror for a project — what Production shows next to
    the 'Approve in pipeline' link (§2.3). Production never hosts the approve."""
    db = principal.tenant_db
    project = await repo.get_project(db, _oid(project_id, "Project"))
    if project is None:
        raise DomainError(NOT_FOUND, "Project not found.", 404)
    rollup = await repo.get_rollup(db, project["_id"])
    sdef = await pm_repo.stage_def_by_key(db, FACTORY_RELEASE_KEY)
    inst = (
        await pm_repo.stage_instance(db, project["_id"], int(sdef["order"]))
        if sdef else None
    )
    release_sections = (sdef or {}).get("release_checklist") or []
    done = (inst or {}).get("checklist_done") or []
    return {
        "project_id": str(project["_id"]),
        "project_code": project.get("code"),
        "sections": (rollup or {}).get("sections") or {},
        "release_checklist": release_sections,
        "checklist_done": done,
        "stage_order": int(sdef["order"]) if sdef else None,
        "stage_status": (inst or {}).get("status"),
        "releasable": bool(inst and set(release_sections) <= set(done)),
    }


# --- station allocation (§3) — manager-gated ---------------------------------


async def _wo_category(db, wo: dict) -> str | None:
    lines = wo.get("bom_lines") or []
    if not lines:
        return None
    try:
        prod = await repo.product(db, ObjectId(str(lines[0]["product_id"])))
    except Exception:
        prod = None
    return (prod or {}).get("category")


async def _auto_station(db, wo: dict) -> str | None:
    """The least-loaded active station whose material types fit the WO — falling
    back to the least-loaded of all active stations when nothing matches."""
    stations = await repo.list_stations(db)
    if not stations:
        return None
    load = await repo.station_load(db, list(ACTIVE_AT_STATION))
    category = await _wo_category(db, wo)
    candidates = [s for s in stations if _station_matches(s, category)] or stations
    best = min(candidates, key=lambda s: load.get(str(s["_id"]), {}).get("units", 0.0))
    return str(best["_id"])


async def allocate_work_order(
    principal: ClientPrincipal, wo_id: str, station_id: str
) -> dict:
    await _require_manager(principal)  # spec §7: production_manager overrides allocation
    db = principal.tenant_db
    actor = str(principal.user["_id"])
    wo = await _wo_or_404(db, wo_id)
    station = await repo.get_station(db, _oid(station_id, "Station"))
    if station is None or not station.get("is_active", True):
        raise DomainError(VALIDATION_ERROR, "Station not found or inactive.", 422)
    route = wo.get("station_route") or []
    if station_id not in route:
        route = [*route, station_id]
    updated = await repo.update_work_order(db, wo["_id"], {
        "current_station_id": station_id, "station_route": route, "updated_by": actor,
    })
    assert updated is not None
    await _log(principal, "production.wo_allocated",
               {"type": "work_order", "id": str(updated["_id"]), "label": updated["code"]},
               {"station": station.get("code")})
    return await _detail(db, updated)


async def auto_allocate_work_order(principal: ClientPrincipal, wo_id: str) -> dict:
    db = principal.tenant_db
    wo = await _wo_or_404(db, wo_id)
    station_id = await _auto_station(db, wo)
    if station_id is None:
        raise DomainError(VALIDATION_ERROR, "No active station to allocate to.", 422)
    return await allocate_work_order(principal, wo_id, station_id)
