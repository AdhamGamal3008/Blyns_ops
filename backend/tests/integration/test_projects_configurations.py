"""Tenant-defined project configurations (docs/PROJECT_CONFIGURATIONS_PLAN.md).

Phase 0 — the data foundation: every stage definition and gate rule belongs to
one VERSION of one CONFIGURATION, a tenant is seeded with the two system configs
that reproduce the original workflow shapes exactly, and a project PINS the
configuration version current when it was created. The CRUD that lets a tenant
build its own configurations lands in Phase 2; the engine reading a project's
pinned version everywhere lands in Phase 1.
"""

from __future__ import annotations

from bson import ObjectId

from app.core.db import get_db_manager
from app.modules.projects import repository as repo
from app.modules.projects import seed as projects_seed

BASE = "/api/v1/projects"


def _tenant_db(onboarded_company):
    return get_db_manager().tenant(onboarded_company["company"]["db_name"])


async def _create_project(client_client, name="Configured build", **extra) -> dict:
    res = await client_client.post(BASE, json={"name": name, **extra})
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _publish_version(db, config, *, stage=None, gate=None) -> int:
    """Stand in for the Phase-2 publish endpoint: copy a configuration's current
    version to version+1, applying the optional `stage`/`gate` mutators to each
    copied doc, and advance `current_version`. The old version is left untouched —
    that immutability is exactly what version-pinning relies on (D1)."""
    scope = repo.scope_of(config)
    assert scope.config_version is not None
    version = scope.config_version + 1

    for source, collection, mutate in (
        (await repo.stage_defs(db, scope), db.stage_definitions, stage),
        (await repo.gate_rules(db, scope), db.gate_rules, gate),
    ):
        for original in source:
            doc = {k: v for k, v in original.items() if k != "_id"}
            doc["config_version"] = version
            if mutate:
                mutate(doc)
            await collection.insert_one(doc)

    await db.project_configurations.update_one(
        {"_id": config["_id"]}, {"$set": {"current_version": version}}
    )
    return version


# --- the two system configurations -------------------------------------------

async def test_tenant_is_seeded_with_two_system_configurations(onboarded_company):
    db = _tenant_db(onboarded_company)
    configs = {c["workflow_shape"]: c for c in await repo.project_configs(db)}

    assert set(configs) == {"sequential", "concurrent"}
    assert all(c["is_system"] for c in configs.values())
    assert all(c["current_version"] == 1 for c in configs.values())
    assert configs["sequential"]["name"] == "Standard"
    assert configs["concurrent"]["name"] == "Concurrent"

    # exactly one default, and it is the sequential one (G-4)
    defaults = [c for c in configs.values() if c.get("is_default")]
    assert [c["workflow_shape"] for c in defaults] == ["sequential"]
    assert (await repo.default_project_config(db))["name"] == "Standard"


async def test_every_definition_is_scoped_to_a_configuration_version(onboarded_company):
    db = _tenant_db(onboarded_company)
    standard = await repo.system_config(db, "sequential")
    concurrent = await repo.system_config(db, "concurrent")

    # 9 stages + 8 gate rules per configuration — a full immutable copy each (§3)
    for config in (standard, concurrent):
        scope = repo.scope_of(config)
        assert len(await repo.stage_defs(db, scope)) == 9
        assert len(await repo.gate_rules(db, scope)) == 8

    assert await db.stage_definitions.count_documents(
        {"configuration_id": {"$exists": False}}
    ) == 0
    assert await db.gate_rules.count_documents(
        {"configuration_id": {"$exists": False}}
    ) == 0


async def test_system_configs_reproduce_the_original_workflow_shapes(onboarded_company):
    """The two shapes survive unchanged as configurations (D-1) — Standard is the
    linear chain, Concurrent fans 2-8 off stage 1 with 9 waiting on all."""
    db = _tenant_db(onboarded_company)
    standard = repo.scope_of(await repo.system_config(db, "sequential"))
    concurrent = repo.scope_of(await repo.system_config(db, "concurrent"))

    seq = {d["order"]: d for d in await repo.stage_defs(db, standard)}
    con = {d["order"]: d for d in await repo.stage_defs(db, concurrent)}
    assert [seq[o]["key"] for o in sorted(seq)] == [con[o]["key"] for o in sorted(con)]

    def _deps(definition):
        return [g["depends_on"] for g in definition["entry_gates"]
                if g.get("type") == "dependency"]

    assert _deps(seq[9]) == [seq[8]["key"]]                     # linear
    assert _deps(con[5]) == [con[1]["key"]]                     # fans off stage 1
    assert set(_deps(con[9])) == {con[o]["key"] for o in range(2, 9)}


async def test_each_configuration_holds_its_own_gate_rule_copies(onboarded_company):
    """G-3 — tuning a threshold on one configuration must never reach another."""
    db = _tenant_db(onboarded_company)
    standard = repo.scope_of(await repo.system_config(db, "sequential"))
    concurrent = repo.scope_of(await repo.system_config(db, "concurrent"))

    rule = await repo.gate_rule(db, "timber_moisture_content", standard)
    other = await repo.gate_rule(db, "timber_moisture_content", concurrent)
    assert rule["_id"] != other["_id"]                      # copies, not one shared doc

    await db.gate_rules.update_one(
        {"_id": rule["_id"]}, {"$set": {"threshold": {"max": 99}}}
    )
    unchanged = await repo.gate_rule(db, "timber_moisture_content", concurrent)
    assert unchanged["threshold"] != {"max": 99}


# --- projects pin a configuration version ------------------------------------

async def test_new_project_pins_the_default_configuration(client_client, onboarded_company):
    db = _tenant_db(onboarded_company)
    project = await _create_project(client_client)
    standard = await repo.system_config(db, "sequential")

    assert project["configuration_id"] == str(standard["_id"])
    assert project["config_version"] == 1
    assert project["workflow_type"] == "sequential"


async def test_project_can_pin_a_named_configuration(client_client, onboarded_company):
    """An explicit configuration_id wins over workflow_type, and its shape is what
    the project runs — the picker Phase 4 builds sends exactly this."""
    db = _tenant_db(onboarded_company)
    concurrent = await repo.system_config(db, "concurrent")

    project = await _create_project(
        client_client, name="Named config", configuration_id=str(concurrent["_id"])
    )
    assert project["configuration_id"] == str(concurrent["_id"])
    assert project["workflow_type"] == "concurrent"     # derived from the config


async def test_workflow_type_still_selects_a_system_configuration(
    client_client, onboarded_company
):
    """Back-compat: a caller that knows only the old enum still lands on the right
    configuration, so the pre-configurations create payload keeps working."""
    db = _tenant_db(onboarded_company)
    project = await _create_project(
        client_client, name="By workflow type", workflow_type="concurrent"
    )
    concurrent = await repo.system_config(db, "concurrent")
    assert project["configuration_id"] == str(concurrent["_id"])


async def test_unknown_configuration_is_rejected(client_client):
    res = await client_client.post(
        BASE, json={"name": "Ghost config", "configuration_id": str(ObjectId())}
    )
    assert res.status_code == 404, res.text


async def test_deactivated_configuration_cannot_start_a_project(
    client_client, onboarded_company
):
    db = _tenant_db(onboarded_company)
    concurrent = await repo.system_config(db, "concurrent")
    await db.project_configurations.update_one(
        {"_id": concurrent["_id"]}, {"$set": {"is_active": False}}
    )
    try:
        res = await client_client.post(
            BASE,
            json={"name": "Retired", "configuration_id": str(concurrent["_id"])},
        )
        assert res.status_code == 422, res.text
    finally:
        await db.project_configurations.update_one(
            {"_id": concurrent["_id"]}, {"$set": {"is_active": True}}
        )


# --- scope resolution ---------------------------------------------------------

async def test_project_resolves_its_stages_through_the_pinned_configuration(
    client_client, onboarded_company
):
    """The Phase-0 'prove': a project's definitions come from the version it
    pinned, and that resolution survives the configuration moving on."""
    db = _tenant_db(onboarded_company)
    project = await _create_project(client_client, name="Pinned")
    doc = await db.projects.find_one({"_id": ObjectId(project["id"])})

    scope = await repo.scope_for_project(db, doc)
    assert scope.configuration_id == doc["configuration_id"]
    assert scope.config_version == 1
    assert len(await repo.stage_defs(db, scope)) == 9

    # publishing a later version must not move the pin (D1) — the project keeps
    # reading v1 even once the configuration's current_version advances
    await db.project_configurations.update_one(
        {"_id": doc["configuration_id"]}, {"$set": {"current_version": 2}}
    )
    still = await repo.scope_for_project(db, doc)
    assert still.config_version == 1


async def test_unpinned_legacy_project_falls_back_to_its_system_config(
    onboarded_company,
):
    """A project created before v4 carries no pin; it resolves to the system config
    matching its workflow_type at version 1 — never at the config's current
    version, which a later publish would have moved (G-5)."""
    db = _tenant_db(onboarded_company)
    concurrent = await repo.system_config(db, "concurrent")
    await db.project_configurations.update_one(
        {"_id": concurrent["_id"]}, {"$set": {"current_version": 7}}
    )

    scope = await repo.scope_for_project(db, {"workflow_type": "concurrent"})
    assert scope.configuration_id == concurrent["_id"]
    assert scope.config_version == 1
    assert len(await repo.stage_defs(db, scope)) == 9


# --- the seed is idempotent and non-destructive -------------------------------

async def test_reseeding_keeps_config_ids_and_tenant_edits(onboarded_company):
    """Re-running the seed must not mint new configurations (projects pin their
    _ids) nor discard a tenant's edits — v4 changes no stage key or order, so it
    adopts what is there instead of resetting it."""
    db = _tenant_db(onboarded_company)
    before = {c["system_key"]: c["_id"] for c in await repo.project_configs(db)}

    standard = repo.scope_of(await repo.system_config(db, "sequential"))
    await db.stage_definitions.update_one(
        {"configuration_id": standard.configuration_id, "key": "site_survey"},
        {"$set": {"name": "Tenant-renamed survey"}},
    )
    await db.approver_role_map.update_one(
        {}, {"$set": {"role_ids": ["tenant-choice"]}}
    )

    await projects_seed.seed(db)

    after = {c["system_key"]: c["_id"] for c in await repo.project_configs(db)}
    assert after == before
    assert await db.stage_definitions.count_documents({}) == 18
    assert await db.gate_rules.count_documents({}) == 16

    renamed = await repo.stage_def_by_key(db, "site_survey", standard)
    assert renamed["name"] == "Tenant-renamed survey"
    entry = await db.approver_role_map.find_one({"role_ids": ["tenant-choice"]})
    assert entry is not None, "a non-skeleton version bump must not reset the map"


# --- the engine reads the pinned version (Phase 1) ---------------------------

async def test_engine_evaluates_each_project_against_its_own_version(
    client_client, onboarded_company
):
    """The Phase-1 'prove': publishing a new version changes what NEW projects
    must satisfy and leaves a running project's stage untouched (D1/G-5)."""
    db = _tenant_db(onboarded_company)
    running = await _create_project(client_client, name="Started on v1")

    def _add_a_document_gate(stage: dict) -> None:
        if stage["key"] == "project_initiation":
            stage["entry_gates"] = [*stage["entry_gates"], {
                "key": "insurance_certificate", "type": "document",
                "label": "Insurance certificate", "blocking": True,
            }]

    version = await _publish_version(
        db, await repo.default_project_config(db), stage=_add_a_document_gate
    )
    fresh = await _create_project(client_client, name="Started on v2")

    assert running["config_version"] == 1
    assert fresh["config_version"] == version == 2

    async def _waiting_on(project):
        res = await client_client.get(f"{BASE}/{project['id']}/stages/1")
        assert res.status_code == 200, res.text
        return res.json()["data"]["evaluation"]["waiting_on"]

    # only the project that pinned v2 waits on the document v2 introduced
    assert "doc:insurance_certificate" not in await _waiting_on(running)
    assert "doc:insurance_certificate" in await _waiting_on(fresh)


async def test_gate_thresholds_come_from_the_pinned_version(
    client_client, onboarded_company
):
    """A published version may retune a gate; a running project keeps scoring
    against the threshold it pinned, not the tenant's current one (G-5)."""
    db = _tenant_db(onboarded_company)
    running = await _create_project(client_client, name="Pinned threshold")

    def _tighten(rule: dict) -> None:
        if rule["key"] == "timber_moisture_content":
            rule["threshold"] = {"min": 0, "max": 1, "unit": "%"}

    await _publish_version(
        db, await repo.default_project_config(db), gate=_tighten
    )
    fresh = await _create_project(client_client, name="Tightened threshold")

    async def _threshold(project):
        doc = await db.projects.find_one({"_id": ObjectId(project["id"])})
        scope = await repo.scope_for_project(db, doc)
        rule = await repo.gate_rule(db, "timber_moisture_content", scope)
        return rule["threshold"]

    assert (await _threshold(running))["max"] == 9      # the version it pinned
    assert (await _threshold(fresh))["max"] == 1        # the version it pinned


async def test_timeline_reports_the_pinned_configuration(
    client_client, onboarded_company
):
    db = _tenant_db(onboarded_company)
    project = await _create_project(client_client, name="Timeline pin")
    standard = await repo.default_project_config(db)

    res = await client_client.get(f"{BASE}/{project['id']}/timeline")
    assert res.status_code == 200, res.text
    timeline = res.json()["data"]

    assert timeline["configuration_id"] == str(standard["_id"])
    assert timeline["config_version"] == 1
    assert len(timeline["stages"]) == 9


async def test_machine_version_is_four(onboarded_company):
    db = _tenant_db(onboarded_company)
    meta = await db.pm_meta.find_one({"_id": "state_machine"})
    assert meta["machine_version"] == 4
