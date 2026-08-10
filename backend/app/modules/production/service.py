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
from app.modules.production.models import WorkOrderConfirm
from app.modules.production.permissions import DONE_STATUSES, QUEUE_DEFAULT_DAYS
from app.modules.projects import engines as pm_engines
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
    return await repo.list_stations(principal.tenant_db)


async def context(principal: ClientPrincipal) -> dict:
    """What the caller may do in Production — drives the UI's manager-only
    affordances without leaking the projects approver map."""
    can_manage = await pm_engines.may_approve(
        principal.tenant_db, "production_manager",
        str(principal.user["_id"]), principal.role.get("name", ""),
    )
    return {"can_manage": can_manage}


# --- generation (D4: auto-propose, manager confirms) -------------------------

def _suggest_station(stations: list[dict], category: str | None) -> str | None:
    """Best-effort entry station from the product category ↔ a station's material
    types. Deliberately light-touch — real routing/allocation is Phase 3."""
    if not category:
        return None
    cat = category.lower()
    for s in stations:
        for mt in s.get("material_types") or []:
            if mt.lower() in cat or cat in mt.lower():
                return str(s["_id"])
    return None


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
