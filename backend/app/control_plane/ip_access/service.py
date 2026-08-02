"""IP access rule admin service (docs/IP_ACCESS_CONTROL_PLAN.md §2-F, P5).

Business rules behind the admin CRUD + the IP-test verdict:
- values are validated/canonicalized by the models (`IpRuleCreate`) — a malformed
  IP/CIDR/country is a 422 before we get here;
- a live rule with the same identity (kind+match_type+value) is a 409 — toggle the
  existing one rather than duplicating it;
- every write is audited to the control audit log AND invalidates the shared
  ruleset cache so the enforcement middleware sees the change immediately;
- the IP tester compiles the CURRENT enabled rules fresh (never via the cache) so
  its verdict is authoritative right after a write — the primary lockout-preventer.
"""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.control_plane.ip_access import repository as repo
from app.control_plane.ip_access.matcher import compile_rules, decide
from app.control_plane.ip_access.models import IpRuleCreate, IpRulePatch
from app.control_plane.ip_access.runtime import get_geo_resolver, invalidate_rule_cache
from app.core.audit import write_admin_audit
from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.errors import (
    IP_RULE_EXISTS,
    TENANT_NOT_FOUND,
    VALIDATION_ERROR,
    DomainError,
)

_AUDIT_TARGET = "ip_access_rule"


async def create_rule(
    control: AsyncIOMotorDatabase, payload: IpRuleCreate, actor_id: str
) -> dict:
    existing = await repo.find_duplicate(
        control, payload.kind, payload.match_type, payload.value
    )
    if existing is not None:
        raise DomainError(
            IP_RULE_EXISTS,
            f"A {payload.kind} rule for {payload.match_type} "
            f"'{payload.value}' already exists.",
            http_status=409,
        )
    doc = await repo.insert(control, {
        "kind": payload.kind,
        "match_type": payload.match_type,
        "value": payload.value,
        "family": payload.family,
        "reason": payload.reason,
        "enabled": payload.enabled,
        "source": "manual",
        "created_by": actor_id,
    })
    await write_admin_audit(
        actor_id=actor_id, action="ip_rule.created",
        target={"type": _AUDIT_TARGET, "id": str(doc["_id"])},
        details={"kind": payload.kind, "match_type": payload.match_type,
                 "value": payload.value, "enabled": payload.enabled},
    )
    invalidate_rule_cache()
    return doc


async def list_rules(
    control: AsyncIOMotorDatabase,
    kind: str | None = None,
    match_type: str | None = None,
    enabled: bool | None = None,
    *,
    skip: int = 0,
    limit: int = 25,
) -> tuple[list[dict], int]:
    """Filtered, newest-first, paginated in memory — the rule set is small and
    admin-managed, so a full fetch + slice is simpler than a paged query."""
    rows = await repo.list_rules(control, kind, match_type, enabled)
    return rows[skip:skip + limit], len(rows)


async def _load(control: AsyncIOMotorDatabase, rule_id: str) -> dict:
    try:
        rule = await repo.get(control, rule_id)
    except Exception as exc:  # malformed ObjectId
        raise DomainError(TENANT_NOT_FOUND, "IP rule not found.", 404) from exc
    if rule is None:
        raise DomainError(TENANT_NOT_FOUND, "IP rule not found.", 404)
    return rule


async def patch_rule(
    control: AsyncIOMotorDatabase, rule_id: str, patch: IpRulePatch, actor_id: str
) -> dict:
    await _load(control, rule_id)
    fields: dict = {}
    if patch.enabled is not None:
        fields["enabled"] = patch.enabled
    if patch.reason is not None:
        fields["reason"] = patch.reason
    if not fields:
        raise DomainError(VALIDATION_ERROR, "Nothing to update.", 422)
    updated = await repo.update(control, rule_id, fields)
    assert updated is not None  # _load already proved it exists
    await write_admin_audit(
        actor_id=actor_id, action="ip_rule.updated",
        target={"type": _AUDIT_TARGET, "id": rule_id}, details=fields,
    )
    invalidate_rule_cache()
    return updated


async def delete_rule(
    control: AsyncIOMotorDatabase, rule_id: str, actor_id: str
) -> None:
    await _load(control, rule_id)
    await repo.soft_delete(control, rule_id, actor_id)
    await write_admin_audit(
        actor_id=actor_id, action="ip_rule.deleted",
        target={"type": _AUDIT_TARGET, "id": rule_id},
    )
    invalidate_rule_cache()


async def test_ip(
    control: AsyncIOMotorDatabase, ip: str, cfg: Settings | None = None
) -> dict:
    """"Would this IP be allowed, and by which rule?" Compiles the CURRENT enabled
    rules fresh (cache-independent) and resolves the country via the geo dataset."""
    cfg = cfg or default_settings
    ruleset = compile_rules(await repo.enabled_rules(control))
    country = get_geo_resolver(cfg).country(ip)
    decision = decide(ip, ruleset, country)
    matched = None
    if decision.rule_id is not None:
        matched = {"id": decision.rule_id, "kind": decision.kind,
                   "match_type": decision.match_type, "value": decision.value}
    return {
        "ip": ip,
        "country": country,
        "allowed": decision.allowed,
        "reason": decision.reason,
        "matched_rule": matched,
    }
