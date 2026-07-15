"""Settings module — tenant seed (docs/modules/SETTINGS.md §3).

This is where the provisioning `seed_rbac` step is implemented: the default
client roles (Owner/Manager/Member/Viewer) over the client resources. The
company profile needs the onboarding payload, so it is seeded by a dedicated
helper the provisioning engine calls with that data.

Idempotent: $setOnInsert upserts never clobber tenant-edited roles/profile.
"""

from __future__ import annotations

from datetime import UTC, datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.shared.enums import Level

# Client resources (docs/AUTH_RBAC.md §2).
CLIENT_RESOURCES = [
    "dashboard", "calendar", "activity",
    "projects", "crm", "inventory", "finance", "settings",
]


def _role(name: str, levels: dict[str, Level]) -> dict:
    """Full resource->Level map; anything unspecified defaults to NONE."""
    permissions = {res: int(levels.get(res, Level.NONE)) for res in CLIENT_RESOURCES}
    return {
        "name": name,
        "permissions": permissions,
        "is_system": True,  # seeded default; still editable, but flagged
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }


def default_roles() -> list[dict]:
    """Default client roles (docs/AUTH_RBAC.md §2). Roles are data — tenants
    edit these maps later through the Settings RBAC editor."""
    w, r = Level.WRITE, Level.READ
    return [
        _role("Owner", {res: w for res in CLIENT_RESOURCES}),
        _role("Manager", {
            "dashboard": r, "calendar": r, "activity": r,
            "projects": w, "crm": w, "inventory": w,   # WRITE ops modules
            "finance": r,                              # READ finance
            "settings": r,
        }),
        _role("Member", {
            "dashboard": r, "calendar": r, "activity": r,
            "projects": w, "crm": w, "inventory": r,
        }),
        _role("Viewer", {"dashboard": r, "calendar": r}),
    ]


async def seed_default_roles(tenant_db: AsyncIOMotorDatabase) -> dict[str, ObjectId]:
    """Upsert the default roles; return {name: role_id} (Owner id is needed by
    the provisioning create_owner_user step)."""
    ids: dict[str, ObjectId] = {}
    for role in default_roles():
        await tenant_db.roles.update_one(
            {"name": role["name"]}, {"$setOnInsert": role}, upsert=True
        )
        doc = await tenant_db.roles.find_one({"name": role["name"]}, {"_id": 1})
        assert doc is not None  # just upserted
        ids[role["name"]] = doc["_id"]
    return ids


async def seed_company_profile(
    tenant_db: AsyncIOMotorDatabase, profile: dict
) -> None:
    """Create the company_profile doc from the onboarding payload
    (docs/modules/SETTINGS.md §1.1). Fixed _id — one per tenant."""
    defaults = {
        "name": profile.get("name", ""),
        "legal_name": profile.get("legal_name", profile.get("name", "")),
        "logo_ref": None,
        "timezone": profile.get("timezone", "UTC"),
        "currency": profile.get("currency", "USD"),
        "fiscal_year_start": profile.get("fiscal_year_start", "01-01"),
        "contact": profile.get("contact", {}),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    await tenant_db.company_profile.update_one(
        {"_id": "company_profile"}, {"$setOnInsert": defaults}, upsert=True
    )


async def seed(tenant_db: AsyncIOMotorDatabase) -> None:
    """Idempotent entry point invoked by the provisioning engine."""
    await tenant_db.roles.create_index("name", unique=True)
    await tenant_db.calendar_events.create_index("start")
    await seed_default_roles(tenant_db)
