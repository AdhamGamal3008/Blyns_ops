"""IP access rule store (docs/IP_ACCESS_CONTROL_PLAN.md §2-A): control-plane
collection, indexes, and the soft-delete/toggle lifecycle the admin API builds on."""

from __future__ import annotations

import pytest

from app.control_plane.ip_access import repository as repo


@pytest.fixture
async def control(db_manager):
    ctrl = db_manager.control
    await ctrl[repo.COLLECTION].delete_many({})
    await repo.ensure_ip_rule_indexes(ctrl)
    return ctrl


async def test_indexes_build(control):
    keys: set[str] = set()
    async for index in control[repo.COLLECTION].list_indexes():
        keys.update(index["key"].keys())
    assert {"kind", "match_type", "enabled", "value"} <= keys


async def test_insert_list_toggle_and_soft_delete(control):
    doc = await repo.insert(control, {
        "kind": "deny", "match_type": "cidr", "value": "203.0.113.0/24",
        "family": 4, "reason": "abuse", "enabled": True, "source": "manual",
        "created_by": "admin1",
    })
    oid = doc["_id"]
    assert doc["is_deleted"] is False

    assert len(await repo.list_rules(control, kind="deny")) == 1
    assert await repo.find_duplicate(control, "deny", "cidr", "203.0.113.0/24") is not None

    # a disabled rule drops out of the matcher's input set
    assert len(await repo.enabled_rules(control)) == 1
    await repo.update(control, oid, {"enabled": False})
    assert await repo.enabled_rules(control) == []

    # soft delete removes it from every live query but keeps the row
    await repo.soft_delete(control, oid, "admin1")
    assert await repo.get(control, oid) is None
    assert await repo.list_rules(control) == []
    assert await repo.find_duplicate(control, "deny", "cidr", "203.0.113.0/24") is None
    assert await control[repo.COLLECTION].count_documents({}) == 1  # audit trail kept
