"""IP access rule seeding (docs/IP_ACCESS_CONTROL_PLAN.md §2-G/§2-H, P6):
production-only, config-driven, idempotent, and respectful of operator edits.
"""

from __future__ import annotations

import pytest

from app.control_plane.ip_access.repository import COLLECTION
from app.control_plane.ip_access.seed import seed_ip_access_rules
from app.core.config import Settings


def _cfg(env: str, **over) -> Settings:
    # kwargs win over the ERP_* test env vars, so env is exactly what we pass.
    return Settings(_env_file=None, jwt_secret="t", env=env, **over)


@pytest.fixture
async def control(db_manager):
    return db_manager.control


async def _clear(control, *values: str) -> None:
    await control[COLLECTION].delete_many({"value": {"$in": list(values)}})


async def test_production_seeds_denylist_and_allowlist(control):
    await _clear(control, "KP", "IR", "203.0.113.5", "198.51.100.0/24")
    cfg = _cfg("production",
               ip_seed_deny_countries=["kp", "IR"],
               ip_seed_allow_ips=["203.0.113.5", "198.51.100.0/24"])

    inserted = await seed_ip_access_rules(control, cfg)
    assert len(inserted) == 4

    kp = await control[COLLECTION].find_one({"match_type": "country", "value": "KP"})
    assert kp is not None and kp["kind"] == "deny" and kp["enabled"] is True
    assert kp["source"] == "seed" and kp["created_by"] == "system:seed"

    net = await control[COLLECTION].find_one({"value": "198.51.100.0/24"})
    assert net["kind"] == "allow" and net["match_type"] == "cidr" and net["family"] == 4
    host = await control[COLLECTION].find_one({"value": "203.0.113.5"})
    assert host["kind"] == "allow" and host["match_type"] == "ip"

    # idempotent — a second seed inserts nothing
    assert await seed_ip_access_rules(control, cfg) == []
    await _clear(control, "KP", "IR", "203.0.113.5", "198.51.100.0/24")


async def test_non_production_seeds_nothing(control):
    await _clear(control, "KP", "203.0.113.5")
    for env in ("local", "test"):
        cfg = _cfg(env, ip_seed_deny_countries=["KP"], ip_seed_allow_ips=["203.0.113.5"])
        assert await seed_ip_access_rules(control, cfg) == []
    assert await control[COLLECTION].find_one({"value": "KP"}) is None
    assert await control[COLLECTION].find_one({"value": "203.0.113.5"}) is None


async def test_reseed_respects_an_operator_disable(control):
    await _clear(control, "KP")
    cfg = _cfg("production", ip_seed_deny_countries=["KP"])
    assert len(await seed_ip_access_rules(control, cfg)) == 1

    # operator disables the seeded rule; re-seeding must not resurrect it
    await control[COLLECTION].update_one({"value": "KP"}, {"$set": {"enabled": False}})
    assert await seed_ip_access_rules(control, cfg) == []
    kp = await control[COLLECTION].find_one({"value": "KP"})
    assert kp["enabled"] is False
    await _clear(control, "KP")


async def test_malformed_entries_are_skipped(control):
    await _clear(control, "KP", "203.0.113.5", "10.0.0.0/8")
    cfg = _cfg("production",
               ip_seed_deny_countries=["KP", "USA", "1"],       # only KP valid
               ip_seed_allow_ips=["203.0.113.5", "not-an-ip", "10.0.0.0/8"])
    inserted = await seed_ip_access_rules(control, cfg)
    assert sorted(r["value"] for r in inserted) == ["10.0.0.0/8", "203.0.113.5", "KP"]
    await _clear(control, "KP", "203.0.113.5", "10.0.0.0/8")
