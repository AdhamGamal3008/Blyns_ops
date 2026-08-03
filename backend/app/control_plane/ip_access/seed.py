"""IP access rule seeding (docs/IP_ACCESS_CONTROL_PLAN.md §2-G/§2-H, P6).

Production-only and config-driven. Two operator-owned lists become `source:"seed"`
rules:

- a **country denylist** (ISO 3166-1 alpha-2) — ships EMPTY; WHICH countries is a
  compliance/legal decision (sanctions/embargo, e.g. OFAC), never baked into code (D6);
- a bootstrap **admin/office allowlist** (IPs/CIDRs) — break-glass so a bad rule can
  never lock every admin out (allowlist-always-wins, D2/D3).

Seeds ONLY when `env == "production"` — local/test are never geo-blocked or
pre-populated. Idempotent: an upsert on rule identity (kind+match_type+value) so
re-seeding never duplicates and `$setOnInsert` never clobbers an operator's later
edit, disable, or delete of a seeded rule.
"""

from __future__ import annotations

from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.control_plane.ip_access.models import normalize_value
from app.control_plane.ip_access.repository import COLLECTION
from app.core.config import Settings

_CREATED_BY = "system:seed"


async def _upsert_seed_rule(
    control_db: AsyncIOMotorDatabase,
    kind: str,
    match_type: str,
    value: str,
    family: int | None,
    reason: str,
) -> bool:
    """Insert the rule only if no rule with this identity exists yet. Returns True
    when newly inserted; `$setOnInsert` leaves any existing rule (manual, or a
    seed rule an operator has since edited/disabled/deleted) untouched."""
    now = datetime.now(UTC)
    result = await control_db[COLLECTION].update_one(
        {"kind": kind, "match_type": match_type, "value": value},
        {"$setOnInsert": {
            "kind": kind, "match_type": match_type, "value": value,
            "family": family, "reason": reason, "enabled": True,
            "source": "seed", "created_by": _CREATED_BY,
            "created_at": now, "updated_at": now, "is_deleted": False,
        }},
        upsert=True,
    )
    return result.upserted_id is not None


async def seed_ip_access_rules(
    control_db: AsyncIOMotorDatabase, cfg: Settings
) -> list[dict]:
    """Seed the configured country denylist + admin allowlist. Returns the rules
    NEWLY inserted (empty in local/test, or in production when both lists are empty
    / already seeded). A malformed entry is skipped, never fatal to the seed."""
    if cfg.env != "production":
        return []
    inserted: list[dict] = []

    for raw in cfg.ip_seed_deny_countries:
        try:
            value, _ = normalize_value("country", raw)
        except ValueError:
            continue
        if await _upsert_seed_rule(
            control_db, "deny", "country", value, None, "seed: sanctioned country"
        ):
            inserted.append({"kind": "deny", "match_type": "country", "value": value})

    for raw in cfg.ip_seed_allow_ips:
        entry = (raw or "").strip()
        match_type = "cidr" if "/" in entry else "ip"
        try:
            value, family = normalize_value(match_type, entry)
        except ValueError:
            continue
        if await _upsert_seed_rule(
            control_db, "allow", match_type, value, family,
            "seed: bootstrap admin/office",
        ):
            inserted.append(
                {"kind": "allow", "match_type": match_type, "value": value}
            )

    return inserted
