"""Project Management v2.0 seed (docs/PROJECT_MANAGEMENT_V2_MIGRATION_PLAN.md §1–3).

Provisioning seeds the 9-stage machine. A machine_version bump on a tenant still
on the old 16-stage machine resets the DEFINITION collections (never runtime data)
before re-seeding — a plain $setOnInsert re-seed would collide on the unique
`order` index and never remove the superseded stages.

Since v4 the collection holds one full copy of the machine per configuration
version (docs/PROJECT_CONFIGURATIONS_PLAN.md), so every assertion here reads ONE
configuration's set — `_standard_stages` — rather than the whole collection.
"""

from __future__ import annotations

from app.core.db import get_db_manager
from app.modules.projects import repository as repo
from app.modules.projects.seed import seed


def _tenant(onboarded_company):
    return get_db_manager().tenant(onboarded_company["company"]["db_name"])


async def _standard_stages(db) -> list[dict]:
    """The default (Standard / sequential) configuration's stage set."""
    return await repo.stage_defs(db, repo.scope_of(await repo.default_project_config(db)))


async def test_fresh_tenant_seeds_the_v2_machine(onboarded_company):
    db = _tenant(onboarded_company)

    stages = await _standard_stages(db)
    assert [s["order"] for s in stages] == list(range(1, 10))
    assert stages[0]["key"] == "project_initiation"
    assert stages[-1]["key"] == "final_inspection_handover"

    # the survey stage auto-advances — no approver, no gate
    survey = next(s for s in stages if s["key"] == "site_survey")
    assert survey.get("auto_advance") is True
    assert survey["approver_role"] is None

    # G1 severe deviation returns the project to the design stage, not on_hold
    mv = next(s for s in stages if s["key"] == "measurement_verification")
    assert mv["recovery"]["action"] == "return_to_stage"
    assert mv["recovery"]["target"] == "design_package"

    roles = {a["approver_role"] async for a in db.approver_role_map.find({})}
    assert roles == {
        "project_director", "design_manager", "engineering",
        "procurement_manager", "production_manager", "project_manager",
    }
    assert "client" not in roles  # client-portal removed in v2.0

    scope = repo.scope_of(await repo.default_project_config(db))
    blocking = {g["key"] for g in await repo.gate_rules(db, scope) if g["blocking"]}
    assert blocking == {
        "deviation_within_tolerance", "concrete_rh_astm_f2170",
        "subfloor_flatness", "timber_moisture_content",
    }
    demoted = {g["key"] for g in await repo.gate_rules(db, scope) if not g["blocking"]}
    assert demoted == {
        "substrate_soundness", "ambient_rh_temp_log",
        "fixing_channel_alignment", "reveal_gap_3mm",
    }

    meta = await db.pm_meta.find_one({"_id": "state_machine"})
    assert meta["machine_version"] == 4


async def test_version_bump_resets_legacy_definitions(onboarded_company):
    db = _tenant(onboarded_company)

    # Simulate a tenant still on the v1 16-stage machine: no version marker, and
    # a legacy stage def whose order (16) does not exist in v2.
    await db.pm_meta.delete_many({})
    await db.stage_definitions.delete_many({})
    await db.stage_definitions.insert_many([
        {"key": "lead_conversion", "order": 1, "approver_role": "project_director"},
        {"key": "client_handover", "order": 16, "approver_role": "project_director"},
    ])

    await seed(db)  # detects v1 → resets definitions → seeds the current machine

    stages = await _standard_stages(db)
    assert len(stages) == 9
    keys = {s["key"] for s in stages}
    assert "project_initiation" in keys
    # the superseded 16-stage definitions are gone from the collection entirely,
    # not merely absent from this configuration's set
    assert await db.stage_definitions.count_documents(
        {"key": {"$in": ["lead_conversion", "client_handover"]}}
    ) == 0
    meta = await db.pm_meta.find_one({"_id": "state_machine"})
    assert meta["machine_version"] == 4
