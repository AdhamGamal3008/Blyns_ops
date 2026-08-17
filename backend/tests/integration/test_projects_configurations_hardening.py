"""Project configurations — Phase 5 (tests + hardening).

Everything here defends the promise the feature is built on: **a project runs the
configuration version it pinned, for its whole life** (D1). The earlier phases
proved that at creation; this proves it survives a full nine-stage lifecycle with
the configuration being edited underneath, and that the surrounding guards —
delete, RBAC, publish races, the migration — hold up.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from bson import ObjectId

from app.core.db import get_db_manager
from app.modules.projects import configurations
from app.modules.projects import repository as repo
from app.modules.projects import seed as projects_seed
from tests.integration.test_projects import (
    _advance,
    _machine_config,
)

BASE = "/api/v1/projects"
CONFIGS = f"{BASE}/config/configurations"
CATALOG = f"{BASE}/config/gate-catalog"

_MIGRATION = Path(__file__).resolve().parents[3] / "scripts" / "migrate_projects_v4.py"


def _tenant_db(onboarded_company):
    return get_db_manager().tenant(onboarded_company["company"]["db_name"])


def _load_migration():
    """Exercise the REAL migration script rather than a copy of its logic — a
    reimplementation here would happily pass while the script itself was broken."""
    spec = importlib.util.spec_from_file_location("migrate_projects_v4", _MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _clone(client_client, name: str, **extra) -> dict:
    res = await client_client.post(CONFIGS, json={"name": name, **extra})
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _publish(client_client, config_id: str, **payload):
    return await client_client.post(f"{CONFIGS}/{config_id}/versions", json=payload)


async def _create_project(client_client, name: str, **extra) -> dict:
    res = await client_client.post(BASE, json={"name": name, **extra})
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _stage(client_client, pid: str, order: int) -> dict:
    res = await client_client.get(f"{BASE}/{pid}/stages/{order}")
    assert res.status_code == 200, res.text
    return res.json()["data"]


# --- the headline guarantee ---------------------------------------------------

async def test_version_pin_survives_a_full_lifecycle(
    client_client, onboarded_company
):
    """Checklist #3 — a running project is untouched by an edit to its
    configuration, all the way to completion.

    The project is driven through every stage while a v2 that adds a blocking
    document AND a quality gate to Stage 5 is published mid-flight. If the pin
    leaked, the project would stall at Stage 5 waiting on evidence that did not
    exist when it started.
    """
    db = _tenant_db(onboarded_company)
    config = await _clone(client_client, "Pinned lifecycle")
    project = await _create_project(
        client_client, "Runs on v1", configuration_id=config["id"]
    )
    pid = project["id"]
    assert project["config_version"] == 1

    # The clone's v1 is a copy of Standard, so the default machine config drives it.
    stages, gates = await _machine_config(client_client)
    for order in (1, 2, 3, 4):
        await _advance(client_client, pid, order, stages, gates)

    # mid-flight, Stage 5 gains a document and a gate in a NEW version
    res = await _publish(client_client, config["id"], stages=[{
        "key": "material_procurement",
        "entry_documents": [
            {"key": "bom_present", "blocking": True},
            {"key": "supplier_astm_cert", "blocking": True},
        ],
        "quality_gates": ["timber_moisture_content"],
    }])
    assert res.status_code == 201, res.text
    assert res.json()["data"]["current_version"] == 2

    # the running project still sees v1's Stage 5 — one document, no quality gate
    stage5 = await _stage(client_client, pid, 5)
    docs = {g["key"] for g in stage5["definition"]["entry_gates"]
            if g["type"] == "document"}
    assert docs == {"bom_present"}
    assert stage5["definition"]["quality_gates"] == []
    assert "doc:supplier_astm_cert" not in stage5["evaluation"]["waiting_on"]

    # ...and it runs to completion on v1 throughout
    for order in (5, 6, 7, 8, 9):
        await _advance(client_client, pid, order, stages, gates)

    finished = await db.projects.find_one({"_id": ObjectId(pid)})
    assert finished["status"] == "completed"
    assert finished["config_version"] == 1          # never moved
    assert finished["configuration_id"] == ObjectId(config["id"])

    # a project started AFTER the publish gets the new requirements. It sits at
    # Stage 1, so its Stage 5 is read through its pinned scope rather than through
    # the stage endpoint (which needs the stage to have been entered).
    fresh = await _create_project(
        client_client, "Runs on v2", configuration_id=config["id"]
    )
    assert fresh["config_version"] == 2
    fresh_doc = await db.projects.find_one({"_id": ObjectId(fresh["id"])})
    fresh_stage5 = await repo.stage_def_by_key(
        db, "material_procurement", await repo.scope_for_project(db, fresh_doc)
    )
    fresh_docs = {g["key"] for g in fresh_stage5["entry_gates"]
                  if g["type"] == "document"}
    assert fresh_docs == {"bom_present", "supplier_astm_cert"}
    assert fresh_stage5["quality_gates"] == ["timber_moisture_content"]


async def test_deleting_a_configuration_cannot_strand_a_completed_project(
    client_client, onboarded_company
):
    """Checklist #4 — the delete guard counts every live project pinned to a
    configuration, not just the active ones: a completed project still needs its
    definitions to render its history."""
    config = await _clone(client_client, "Has history")
    project = await _create_project(
        client_client, "Will complete", configuration_id=config["id"]
    )
    stages, gates = await _machine_config(client_client)
    for order in range(1, 10):
        await _advance(client_client, project["id"], order, stages, gates)

    res = await client_client.delete(f"{CONFIGS}/{config['id']}")
    assert res.status_code == 422, res.text

    # its timeline still resolves all nine stages
    timeline = (await client_client.get(f"{BASE}/{project['id']}/timeline")).json()["data"]
    assert len(timeline["stages"]) == 9
    assert timeline["config_version"] == 1


# --- publishing under stress ---------------------------------------------------

async def test_publish_numbering_steps_over_debris_from_a_failed_write(
    client_client, onboarded_company
):
    """A publish that died partway leaves stage docs at a version the configuration
    never adopted. Numbering the next publish from the highest version PRESENT (not
    from current_version) means the retry lands on a free number instead of
    colliding with that debris forever."""
    db = _tenant_db(onboarded_company)
    config = await _clone(client_client, "Interrupted")
    cid = ObjectId(config["id"])

    # simulate the debris: a half-written v2 that current_version never reached
    orphan = await db.stage_definitions.find_one(
        {"configuration_id": cid, "config_version": 1}
    )
    await db.stage_definitions.insert_one(
        {**{k: v for k, v in orphan.items() if k != "_id"}, "config_version": 2}
    )
    assert (await db.project_configurations.find_one({"_id": cid}))["current_version"] == 1

    res = await _publish(client_client, config["id"])
    assert res.status_code == 201, res.text
    assert res.json()["data"]["current_version"] == 3    # stepped over the debris
    assert await db.stage_definitions.count_documents(
        {"configuration_id": cid, "config_version": 3}
    ) == 9


async def test_racing_publish_is_rejected_rather_than_silently_lost(
    client_client, onboarded_company, monkeypatch
):
    """Two editors publishing at once: the compound unique index catches the loser.

    The race is only real if the winner lands BETWEEN the loser's version read and
    its write — planting the winner's docs beforehand would just be debris, which
    the numbering steps over. So the winner is injected inside `_write_version`.
    The loser must be told to reload: silently overwriting the winner's version
    would lose a published change with nobody the wiser.
    """
    db = _tenant_db(onboarded_company)
    config = await _clone(client_client, "Contended")
    cid = ObjectId(config["id"])
    real_write = configurations._write_version

    async def _winner_gets_there_first(database, config_id, version, stages, gates):
        monkeypatch.undo()                       # only the first publish races
        await database[repo.STAGE_DEFS].insert_one({
            "configuration_id": config_id, "config_version": version,
            "key": "project_initiation", "order": 1, "name": "Winner's copy",
        })
        return await real_write(database, config_id, version, stages, gates)

    monkeypatch.setattr(configurations, "_write_version", _winner_gets_there_first)

    res = await _publish(client_client, config["id"])
    assert res.status_code == 409, res.text
    assert "published by someone else" in res.json()["error"]["message"]

    # the loser adopted nothing — the configuration still points where it did
    assert (await db.project_configurations.find_one({"_id": cid}))["current_version"] == 1

    # and the loser can retry: numbering steps over the half-written version
    retry = await _publish(client_client, config["id"])
    assert retry.status_code == 201, retry.text
    assert retry.json()["data"]["current_version"] == 3


# --- migration ------------------------------------------------------------------

async def test_migration_is_idempotent(onboarded_company):
    """Checklist #6 — running the real v4 migration twice must not mint a second
    pair of system configs, duplicate any definitions, or re-pin a project."""
    db = _tenant_db(onboarded_company)
    migration = _load_migration()

    configs = {
        c["workflow_shape"]: c
        async for c in db.project_configurations.find({"is_system": True})
    }
    project = await db.projects.insert_one({
        "name": "Pre-existing", "code": "OLD-0", "workflow_type": "sequential",
        "configuration_id": None, "status": "active", "is_deleted": False,
    })

    first = await migration._pin_projects(db, configs)
    assert first == 1

    before = {
        "configs": [c["_id"] async for c in db.project_configurations.find({})],
        "stages": await db.stage_definitions.count_documents({}),
        "gates": await db.gate_rules.count_documents({}),
        "catalog": await db.gate_catalog.count_documents({}),
    }

    # a full second pass: re-seed AND re-pin
    await projects_seed.seed(db)
    second = await migration._pin_projects(db, configs)
    assert second == 0                       # nothing left unpinned to move

    assert [c["_id"] async for c in db.project_configurations.find({})] == before["configs"]
    assert await db.stage_definitions.count_documents({}) == before["stages"]
    assert await db.gate_rules.count_documents({}) == before["gates"]
    assert await db.gate_catalog.count_documents({}) == before["catalog"]

    pinned = await db.projects.find_one({"_id": project.inserted_id})
    assert pinned["configuration_id"] == configs["sequential"]["_id"]
    assert pinned["config_version"] == 1


async def test_migration_pins_each_project_to_its_own_shape(onboarded_company):
    """A tenant's concurrent projects must land on the Concurrent configuration and
    its sequential ones on Standard — mixing them up would change how a running
    project's stages unlock."""
    db = _tenant_db(onboarded_company)
    migration = _load_migration()
    configs = {
        c["workflow_shape"]: c
        async for c in db.project_configurations.find({"is_system": True})
    }

    # `code` is uniquely indexed, so these stand-ins need distinct ones
    await db.projects.insert_many([
        {"name": "seq", "code": "OLD-1", "workflow_type": "sequential",
         "is_deleted": False},
        {"name": "con", "code": "OLD-2", "workflow_type": "concurrent",
         "is_deleted": False},
        # predates workflow_type entirely — it is the sequential machine
        {"name": "ancient", "code": "OLD-3", "is_deleted": False},
    ])
    assert await migration._pin_projects(db, configs) == 3

    for name, shape in (("seq", "sequential"), ("con", "concurrent"),
                        ("ancient", "sequential")):
        doc = await db.projects.find_one({"name": name})
        assert doc["configuration_id"] == configs[shape]["_id"], name
        assert doc["config_version"] == 1
        assert doc["workflow_type"] == shape

    # and each resolves the right stage set through its pin
    concurrent = await db.projects.find_one({"name": "con"})
    scope = await repo.scope_for_project(db, concurrent)
    stage9 = await repo.stage_def_by_key(db, "final_inspection_handover", scope)
    deps = [g["depends_on"] for g in stage9["entry_gates"]
            if g.get("type") == "dependency"]
    assert len(deps) == 7                     # the parallel DAG, not the linear chain


# --- RBAC (checklist: every management route is settings WRITE) ----------------

async def test_every_management_route_requires_settings_write(
    client_client, onboarded_company
):
    """§4 — `projects` WRITE is not enough to build configurations; that is
    tenant-admin work guarded exactly like the approver map."""
    db = _tenant_db(onboarded_company)
    config = await _clone(client_client, "Guarded")
    await db.roles.update_one({"name": "Owner"}, {"$set": {"permissions.settings": 2}})

    forbidden = [
        ("GET", f"{CONFIGS}/{config['id']}", None),
        ("POST", CONFIGS, {"name": "Nope"}),
        ("PATCH", f"{CONFIGS}/{config['id']}", {"name": "Renamed"}),
        ("DELETE", f"{CONFIGS}/{config['id']}", None),
        ("POST", f"{CONFIGS}/{config['id']}/versions", {}),
        ("GET", CATALOG, None),
        ("POST", CATALOG, {"key": "x", "name": "X", "threshold": {"max": 1}}),
        ("DELETE", f"{CATALOG}/timber_moisture_content", None),
    ]
    for method, url, body in forbidden:
        res = await client_client.request(method, url, json=body)
        assert res.status_code == 403, f"{method} {url} -> {res.status_code}"

    # the Stage-1 picker stays readable on `projects` READ alone
    assert (await client_client.get(f"{CONFIGS}?active_only=true")).status_code == 200
