"""CRM business logic (docs/modules/CRM.md §2).

Every mutation writes the tenant activity_log (CLAUDE.md rule 4), which is what
the Dashboard's activity panel reads. Deals and CRM activities also feed the
Dashboard calendar — the document shape here must keep matching what
modules/dashboard/repository.py:calendar_crm() queries.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId

from app.core.audit import write_activity
from app.core.errors import TENANT_NOT_FOUND, VALIDATION_ERROR, DomainError
from app.modules.crm import repository as repo
from app.modules.crm.models import (
    AccountCreate,
    AccountPatch,
    ActivityCreate,
    ActivityPatch,
    ContactCreate,
    ContactPatch,
    DealCreate,
    DealPatch,
    DealStageChange,
    LeadConvert,
    LeadCreate,
    LeadPatch,
)
from app.modules.crm.permissions import STAGES, TERMINAL_STAGES
from app.tenant.deps import ClientPrincipal

_COLL_FOR_ENTITY = {
    "account": repo.ACCOUNTS,
    "contact": repo.CONTACTS,
    "lead": repo.LEADS,
    "deal": repo.DEALS,
}


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
        module="crm",
    )


def _oid(value: str, what: str) -> ObjectId:
    try:
        return ObjectId(value)
    except Exception as exc:
        raise DomainError(TENANT_NOT_FOUND, f"{what} not found.", 404) from exc


def _owner(principal: ClientPrincipal, explicit: str | None) -> str:
    return explicit or str(principal.user["_id"])


async def _require(principal: ClientPrincipal, coll: str, oid: ObjectId, what: str) -> dict:
    doc = await repo.get(principal.tenant_db, coll, oid)
    if doc is None:
        raise DomainError(TENANT_NOT_FOUND, f"{what} not found.", 404)
    return doc


def _owner_filter(principal: ClientPrincipal, owner: str | None) -> dict:
    """List views support "mine vs all" (§2). Default is tenant-wide visibility
    for READ users — row-level restriction stays a Settings concern."""
    if owner == "mine":
        return {"owner_id": str(principal.user["_id"])}
    return {}


# --- accounts ----------------------------------------------------------------

async def list_accounts(
    principal: ClientPrincipal, owner: str | None, status: str | None,
    q: str | None, skip: int, limit: int,
) -> tuple[list[dict], int]:
    query: dict[str, Any] = _owner_filter(principal, owner)
    if status:
        query["status"] = status
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    return await repo.list_docs(principal.tenant_db, repo.ACCOUNTS, query, skip, limit)


async def create_account(principal: ClientPrincipal, payload: AccountCreate) -> dict:
    doc = payload.model_dump()
    doc["owner_id"] = _owner(principal, payload.owner_id)
    doc["created_by"] = str(principal.user["_id"])
    doc = await repo.insert(principal.tenant_db, repo.ACCOUNTS, doc)
    await _log(principal, "crm.account.created",
               {"type": "account", "id": str(doc["_id"]), "label": doc["name"]})
    return doc


async def patch_account(
    principal: ClientPrincipal, account_id: str, patch: AccountPatch
) -> dict:
    oid = _oid(account_id, "Account")
    account = await _require(principal, repo.ACCOUNTS, oid, "Account")
    fields = {k: v for k, v in patch.model_dump(exclude_unset=True).items() if v is not None}
    if not fields:
        return account
    fields["updated_by"] = str(principal.user["_id"])
    updated = await repo.update(principal.tenant_db, repo.ACCOUNTS, oid, fields)
    assert updated is not None
    await _log(principal, "crm.account.updated",
               {"type": "account", "id": account_id, "label": updated["name"]},
               {"fields": [k for k in fields if k != "updated_by"]})
    return updated


async def delete_account(principal: ClientPrincipal, account_id: str) -> None:
    oid = _oid(account_id, "Account")
    account = await _require(principal, repo.ACCOUNTS, oid, "Account")
    open_deals = await repo.count_by(
        principal.tenant_db, repo.DEALS,
        {"account_id": oid, "stage": {"$nin": list(TERMINAL_STAGES)}},
    )
    if open_deals:
        raise DomainError(
            VALIDATION_ERROR,
            f"Account has {open_deals} open deal(s); close or reassign them first.",
            http_status=409,
        )
    await repo.soft_delete(
        principal.tenant_db, repo.ACCOUNTS, oid, str(principal.user["_id"])
    )
    await _log(principal, "crm.account.deleted",
               {"type": "account", "id": account_id, "label": account["name"]})


# --- contacts ----------------------------------------------------------------

async def list_contacts(
    principal: ClientPrincipal, owner: str | None, account_id: str | None,
    q: str | None, skip: int, limit: int,
) -> tuple[list[dict], int]:
    query: dict[str, Any] = _owner_filter(principal, owner)
    if account_id:
        query["account_id"] = _oid(account_id, "Account")
    if q:
        query["$or"] = [
            {"first_name": {"$regex": q, "$options": "i"}},
            {"last_name": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
        ]
    return await repo.list_docs(principal.tenant_db, repo.CONTACTS, query, skip, limit)


async def create_contact(principal: ClientPrincipal, payload: ContactCreate) -> dict:
    doc = payload.model_dump()
    if payload.account_id:
        aoid = _oid(payload.account_id, "Account")
        await _require(principal, repo.ACCOUNTS, aoid, "Account")
        doc["account_id"] = aoid
    doc["owner_id"] = _owner(principal, payload.owner_id)
    doc["created_by"] = str(principal.user["_id"])
    doc = await repo.insert(principal.tenant_db, repo.CONTACTS, doc)
    await _log(principal, "crm.contact.created",
               {"type": "contact", "id": str(doc["_id"]),
                "label": f"{doc['first_name']} {doc['last_name']}"})
    return doc


async def patch_contact(
    principal: ClientPrincipal, contact_id: str, patch: ContactPatch
) -> dict:
    oid = _oid(contact_id, "Contact")
    contact = await _require(principal, repo.CONTACTS, oid, "Contact")
    fields = {k: v for k, v in patch.model_dump(exclude_unset=True).items() if v is not None}
    if "account_id" in fields:
        aoid = _oid(fields["account_id"], "Account")
        await _require(principal, repo.ACCOUNTS, aoid, "Account")
        fields["account_id"] = aoid
    if not fields:
        return contact
    fields["updated_by"] = str(principal.user["_id"])
    updated = await repo.update(principal.tenant_db, repo.CONTACTS, oid, fields)
    assert updated is not None
    await _log(principal, "crm.contact.updated",
               {"type": "contact", "id": contact_id,
                "label": f"{updated['first_name']} {updated['last_name']}"},
               {"fields": [k for k in fields if k != "updated_by"]})
    return updated


async def delete_contact(principal: ClientPrincipal, contact_id: str) -> None:
    oid = _oid(contact_id, "Contact")
    contact = await _require(principal, repo.CONTACTS, oid, "Contact")
    await repo.soft_delete(
        principal.tenant_db, repo.CONTACTS, oid, str(principal.user["_id"])
    )
    await _log(principal, "crm.contact.deleted",
               {"type": "contact", "id": contact_id,
                "label": f"{contact['first_name']} {contact['last_name']}"})


# --- leads -------------------------------------------------------------------

async def list_leads(
    principal: ClientPrincipal, owner: str | None, status: str | None,
    q: str | None, skip: int, limit: int,
) -> tuple[list[dict], int]:
    query: dict[str, Any] = _owner_filter(principal, owner)
    if status:
        query["status"] = status
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    return await repo.list_docs(principal.tenant_db, repo.LEADS, query, skip, limit)


async def create_lead(principal: ClientPrincipal, payload: LeadCreate) -> dict:
    doc = payload.model_dump()
    doc["owner_id"] = _owner(principal, payload.owner_id)
    doc["created_by"] = str(principal.user["_id"])
    doc["converted_to"] = {"account_id": None, "contact_id": None, "deal_id": None}
    doc = await repo.insert(principal.tenant_db, repo.LEADS, doc)
    await _log(principal, "crm.lead.created",
               {"type": "lead", "id": str(doc["_id"]), "label": doc["name"]})
    return doc


async def patch_lead(principal: ClientPrincipal, lead_id: str, patch: LeadPatch) -> dict:
    oid = _oid(lead_id, "Lead")
    lead = await _require(principal, repo.LEADS, oid, "Lead")
    if lead.get("status") == "converted":
        raise DomainError(
            VALIDATION_ERROR, "A converted lead can no longer be edited.", 409
        )
    fields = {k: v for k, v in patch.model_dump(exclude_unset=True).items() if v is not None}
    if fields.get("status") == "converted":
        raise DomainError(
            VALIDATION_ERROR,
            "Use POST /crm/leads/{id}/convert to convert a lead.", 422,
        )
    if not fields:
        return lead
    fields["updated_by"] = str(principal.user["_id"])
    updated = await repo.update(principal.tenant_db, repo.LEADS, oid, fields)
    assert updated is not None
    await _log(principal, "crm.lead.updated",
               {"type": "lead", "id": lead_id, "label": updated["name"]},
               {"fields": [k for k in fields if k != "updated_by"]})
    return updated


async def delete_lead(principal: ClientPrincipal, lead_id: str) -> None:
    oid = _oid(lead_id, "Lead")
    lead = await _require(principal, repo.LEADS, oid, "Lead")
    await repo.soft_delete(
        principal.tenant_db, repo.LEADS, oid, str(principal.user["_id"])
    )
    await _log(principal, "crm.lead.deleted",
               {"type": "lead", "id": lead_id, "label": lead["name"]})


def _split_name(full: str) -> tuple[str, str]:
    parts = full.strip().split(None, 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (full.strip(), "—")


async def convert_lead(
    principal: ClientPrincipal, lead_id: str, payload: LeadConvert
) -> dict:
    """Acceptance #1: creates/links account + contact + deal and stamps
    `converted_to`.

    A standalone mongod offers no multi-document transaction, so this
    compensates on failure (deleting what it just created) rather than relying
    on one — the same idiom the seat claim uses in modules/settings/service.py.
    """
    oid = _oid(lead_id, "Lead")
    lead = await _require(principal, repo.LEADS, oid, "Lead")
    if lead.get("status") == "converted":
        raise DomainError(VALIDATION_ERROR, "Lead is already converted.", 409)

    db = principal.tenant_db
    actor = str(principal.user["_id"])
    owner_id = lead.get("owner_id") or actor
    created: list[tuple[str, ObjectId]] = []

    try:
        # 1. account — link an existing one, or create from the payload/lead name
        if payload.account_id:
            account = await _require(
                principal, repo.ACCOUNTS, _oid(payload.account_id, "Account"), "Account"
            )
        else:
            account = await repo.insert(db, repo.ACCOUNTS, {
                "name": payload.account_name or lead["name"],
                "industry": None, "website": None, "phone": lead.get("phone"),
                "address": None, "status": "customer", "tags": [],
                "owner_id": owner_id, "created_by": actor,
            })
            created.append((repo.ACCOUNTS, account["_id"]))

        # 2. contact
        first, last = _split_name(lead["name"])
        contact = await repo.insert(db, repo.CONTACTS, {
            "account_id": account["_id"], "first_name": first, "last_name": last,
            "email": lead.get("email"), "phone": lead.get("phone"), "title": None,
            "tags": [], "owner_id": owner_id, "created_by": actor,
        })
        created.append((repo.CONTACTS, contact["_id"]))

        # 3. deal
        deal = await repo.insert(db, repo.DEALS, {
            "title": payload.deal_title or f"{lead['name']} — new business",
            "account_id": account["_id"], "contact_id": contact["_id"],
            "pipeline": "default", "stage": "new",
            "amount": payload.amount, "currency": payload.currency,
            "probability_pct": 0,
            "expected_close_date": payload.expected_close_date,
            "owner_id": owner_id, "lost_reason": None, "created_by": actor,
        })
        created.append((repo.DEALS, deal["_id"]))

        # 4. stamp the lead
        converted_to = {
            "account_id": str(account["_id"]),
            "contact_id": str(contact["_id"]),
            "deal_id": str(deal["_id"]),
        }
        updated = await repo.update(db, repo.LEADS, oid, {
            "status": "converted", "converted_to": converted_to,
            "updated_by": actor,
        })
        assert updated is not None
    except Exception:
        for coll, doc_id in reversed(created):
            await repo.hard_delete(db, coll, doc_id)
        raise

    await _log(principal, "crm.lead.converted",
               {"type": "lead", "id": lead_id, "label": lead["name"]},
               converted_to)
    return {"lead": updated, "account": account, "contact": contact, "deal": deal}


# --- deals -------------------------------------------------------------------

async def list_deals(
    principal: ClientPrincipal, owner: str | None, stage: str | None,
    account_id: str | None, skip: int, limit: int, pipeline: str | None = None,
) -> tuple[list[dict], int]:
    query: dict[str, Any] = _owner_filter(principal, owner)
    if pipeline:
        query.update(repo.pipeline_match(pipeline))
    if stage:
        query["stage"] = stage
    if account_id:
        query["account_id"] = _oid(account_id, "Account")
    return await repo.list_docs(
        principal.tenant_db, repo.DEALS, query, skip, limit,
        sort=[("expected_close_date", 1), ("created_at", -1)],
    )


async def create_deal(principal: ClientPrincipal, payload: DealCreate) -> dict:
    if payload.stage == "lost" and not payload.lost_reason:
        raise DomainError(
            VALIDATION_ERROR, "A lost deal requires `lost_reason`.", 422
        )
    doc = payload.model_dump()
    for key, what in (("account_id", "Account"), ("contact_id", "Contact")):
        if doc.get(key):
            coll = repo.ACCOUNTS if key == "account_id" else repo.CONTACTS
            ref = _oid(doc[key], what)
            await _require(principal, coll, ref, what)
            doc[key] = ref
    doc["owner_id"] = _owner(principal, payload.owner_id)
    doc["created_by"] = str(principal.user["_id"])
    doc = await repo.insert(principal.tenant_db, repo.DEALS, doc)
    await _log(principal, "crm.deal.created",
               {"type": "deal", "id": str(doc["_id"]), "label": doc["title"]},
               {"stage": doc["stage"], "amount": doc["amount"]})
    return doc


async def patch_deal(principal: ClientPrincipal, deal_id: str, patch: DealPatch) -> dict:
    oid = _oid(deal_id, "Deal")
    deal = await _require(principal, repo.DEALS, oid, "Deal")
    fields = {k: v for k, v in patch.model_dump(exclude_unset=True).items() if v is not None}
    for key, what in (("account_id", "Account"), ("contact_id", "Contact")):
        if key in fields:
            coll = repo.ACCOUNTS if key == "account_id" else repo.CONTACTS
            ref = _oid(fields[key], what)
            await _require(principal, coll, ref, what)
            fields[key] = ref
    if not fields:
        return deal
    fields["updated_by"] = str(principal.user["_id"])
    updated = await repo.update(principal.tenant_db, repo.DEALS, oid, fields)
    assert updated is not None
    await _log(principal, "crm.deal.updated",
               {"type": "deal", "id": deal_id, "label": updated["title"]},
               {"fields": [k for k in fields if k != "updated_by"]})
    return updated


async def change_deal_stage(
    principal: ClientPrincipal, deal_id: str, payload: DealStageChange
) -> dict:
    """Acceptance #2: `lost` without a reason is rejected. `won`/`lost` are
    terminal, and the move is recorded as `crm.deal.stage_changed` (§2)."""
    oid = _oid(deal_id, "Deal")
    deal = await _require(principal, repo.DEALS, oid, "Deal")
    old_stage = deal["stage"]

    if payload.stage == "lost" and not (payload.lost_reason or "").strip():
        raise DomainError(
            VALIDATION_ERROR, "Moving a deal to `lost` requires `lost_reason`.", 422
        )
    if old_stage in TERMINAL_STAGES:
        raise DomainError(
            VALIDATION_ERROR,
            f"Deal is already {old_stage}; terminal stages cannot be reopened.",
            http_status=409,
        )
    if payload.stage == old_stage:
        return deal

    fields: dict[str, Any] = {
        "stage": payload.stage, "updated_by": str(principal.user["_id"])
    }
    fields["lost_reason"] = payload.lost_reason if payload.stage == "lost" else None
    if payload.stage == "won":
        fields["probability_pct"] = 100
        fields["closed_at"] = datetime.now(UTC)
    elif payload.stage == "lost":
        fields["probability_pct"] = 0
        fields["closed_at"] = datetime.now(UTC)

    updated = await repo.update(principal.tenant_db, repo.DEALS, oid, fields)
    assert updated is not None
    await _log(principal, "crm.deal.stage_changed",
               {"type": "deal", "id": deal_id, "label": deal["title"]},
               {"from": old_stage, "to": payload.stage,
                "lost_reason": payload.lost_reason})
    return updated


async def delete_deal(principal: ClientPrincipal, deal_id: str) -> None:
    oid = _oid(deal_id, "Deal")
    deal = await _require(principal, repo.DEALS, oid, "Deal")
    await repo.soft_delete(
        principal.tenant_db, repo.DEALS, oid, str(principal.user["_id"])
    )
    await _log(principal, "crm.deal.deleted",
               {"type": "deal", "id": deal_id, "label": deal["title"]})


async def get_pipeline(principal: ClientPrincipal, key: str) -> dict:
    """Acceptance #3: stage buckets with counts and summed amounts."""
    db = principal.tenant_db
    definition = await db.pipelines.find_one({"key": key})
    if definition is None:
        raise DomainError(TENANT_NOT_FOUND, "Pipeline not found.", 404)
    stages: list[str] = definition.get("stages") or STAGES
    buckets = await repo.pipeline_buckets(db, key)
    return {
        "pipeline": key,
        "name": definition.get("name", key),
        "stages": [
            {
                "stage": s,
                "count": buckets.get(s, {}).get("count", 0),
                "amount": buckets.get(s, {}).get("amount", 0.0),
                "is_terminal": s in TERMINAL_STAGES,
            }
            for s in stages
        ],
        "open_value": await repo.open_deal_value(db),
    }


# --- activities --------------------------------------------------------------

async def list_activities(
    principal: ClientPrincipal, owner: str | None, entity_id: str | None,
    done: bool | None, skip: int, limit: int,
) -> tuple[list[dict], int]:
    query: dict[str, Any] = _owner_filter(principal, owner)
    if entity_id:
        query["entity_ref.id"] = entity_id
    if done is not None:
        query["done"] = done
    return await repo.list_docs(
        principal.tenant_db, repo.ACTIVITIES, query, skip, limit,
        sort=[("due_at", 1), ("created_at", -1)],
    )


async def create_activity(principal: ClientPrincipal, payload: ActivityCreate) -> dict:
    ref = payload.entity_ref
    coll = _COLL_FOR_ENTITY[ref.type]
    await _require(principal, coll, _oid(ref.id, ref.type.title()), ref.type.title())
    doc = payload.model_dump()
    doc["entity_ref"] = {"type": ref.type, "id": ref.id}
    doc["owner_id"] = _owner(principal, payload.owner_id)
    doc["created_by"] = str(principal.user["_id"])
    doc = await repo.insert(principal.tenant_db, repo.ACTIVITIES, doc)
    await _log(principal, "crm.activity.created",
               {"type": "activity", "id": str(doc["_id"]), "label": doc["subject"]},
               {"entity": doc["entity_ref"], "activity_type": doc["type"]})
    return doc


async def patch_activity(
    principal: ClientPrincipal, activity_id: str, patch: ActivityPatch
) -> dict:
    oid = _oid(activity_id, "Activity")
    activity = await _require(principal, repo.ACTIVITIES, oid, "Activity")
    fields = {k: v for k, v in patch.model_dump(exclude_unset=True).items() if v is not None}
    if not fields:
        return activity
    fields["updated_by"] = str(principal.user["_id"])
    updated = await repo.update(principal.tenant_db, repo.ACTIVITIES, oid, fields)
    assert updated is not None
    await _log(principal, "crm.activity.updated",
               {"type": "activity", "id": activity_id, "label": updated["subject"]},
               {"fields": [k for k in fields if k != "updated_by"]})
    return updated


async def delete_activity(principal: ClientPrincipal, activity_id: str) -> None:
    oid = _oid(activity_id, "Activity")
    activity = await _require(principal, repo.ACTIVITIES, oid, "Activity")
    await repo.soft_delete(
        principal.tenant_db, repo.ACTIVITIES, oid, str(principal.user["_id"])
    )
    await _log(principal, "crm.activity.deleted",
               {"type": "activity", "id": activity_id, "label": activity["subject"]})
