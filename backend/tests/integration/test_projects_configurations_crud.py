"""Project configuration CRUD, versioning and the gate catalog — Phase 2
(docs/PROJECT_CONFIGURATIONS_PLAN.md §5).

A configuration is created by CLONING and edited by PUBLISHING an immutable new
version. The headline guarantee these tests exist to protect: publishing changes
what NEW projects run, and can never move a project already in flight (D1).
"""

from __future__ import annotations

from bson import ObjectId

from app.core.db import get_db_manager
from app.modules.projects import repository as repo

BASE = "/api/v1/projects"
CONFIGS = f"{BASE}/config/configurations"
CATALOG = f"{BASE}/config/gate-catalog"


def _tenant_db(onboarded_company):
    return get_db_manager().tenant(onboarded_company["company"]["db_name"])


async def _configs(client_client) -> dict[str, dict]:
    res = await client_client.get(CONFIGS)
    assert res.status_code == 200, res.text
    return {c["name"]: c for c in res.json()["data"]}


async def _clone(client_client, name="Flooring — ASTM", **extra) -> dict:
    res = await client_client.post(CONFIGS, json={"name": name, **extra})
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _publish(client_client, config_id, **payload) -> dict:
    res = await client_client.post(f"{CONFIGS}/{config_id}/versions", json=payload)
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _create_project(client_client, name, **extra) -> dict:
    res = await client_client.post(BASE, json={"name": name, **extra})
    assert res.status_code == 201, res.text
    return res.json()["data"]


# --- listing & cloning --------------------------------------------------------

async def test_lists_the_seeded_system_configurations(client_client):
    configs = await _configs(client_client)
    assert set(configs) == {"Standard", "Concurrent"}
    assert configs["Standard"]["is_default"] is True
    assert all(c["is_system"] for c in configs.values())


async def test_clone_copies_the_full_machine_at_version_one(
    client_client, onboarded_company
):
    db = _tenant_db(onboarded_company)
    clone = await _clone(client_client)

    assert clone["current_version"] == 1
    assert clone["is_system"] is False
    assert clone["is_default"] is False
    assert clone["workflow_shape"] == "sequential"      # inherited from the base

    scope = repo.ConfigScope(ObjectId(clone["id"]), 1, "sequential")
    assert len(await repo.stage_defs(db, scope)) == 9
    assert len(await repo.gate_rules(db, scope)) == 8

    # G-3: the clone owns its docs — it does not share the base's
    standard = await repo.system_config(db, "sequential")
    base_ids = {d["_id"] for d in await repo.stage_defs(db, repo.scope_of(standard))}
    clone_ids = {d["_id"] for d in await repo.stage_defs(db, scope)}
    assert not (base_ids & clone_ids)


async def test_clone_can_name_its_base(client_client, onboarded_company):
    db = _tenant_db(onboarded_company)
    concurrent = await repo.system_config(db, "concurrent")
    clone = await _clone(
        client_client, name="Fast-track joinery",
        base_configuration_id=str(concurrent["_id"]),
    )
    assert clone["workflow_shape"] == "concurrent"
    assert clone["cloned_from"] == str(concurrent["_id"])


async def test_get_configuration_returns_its_current_version(client_client):
    clone = await _clone(client_client)
    res = await client_client.get(f"{CONFIGS}/{clone['id']}")
    assert res.status_code == 200, res.text
    data = res.json()["data"]

    assert len(data["stages"]) == 9
    assert len(data["gates"]) == 8
    assert [s["order"] for s in data["stages"]] == list(range(1, 10))


# --- publishing a version -----------------------------------------------------

async def test_publish_creates_an_immutable_new_version(
    client_client, onboarded_company
):
    """The Phase-2 'prove': clone → retune a threshold + attach a gate → publish
    v2 → a NEW project sees v2 while an OLD project still sees v1."""
    db = _tenant_db(onboarded_company)
    clone = await _clone(client_client)

    # a project started on v1, before the edit
    before = await _create_project(
        client_client, "Started on v1", configuration_id=clone["id"]
    )

    published = await _publish(
        client_client, clone["id"],
        stages=[{
            "key": "project_initiation",
            "entry_documents": [
                {"key": "loi_or_po", "blocking": True},
                {"key": "insurance_certificate", "label": "Insurance", "blocking": True},
            ],
            # attach a gate to a stage that had none — the gap this feature closes
            "quality_gates": ["timber_moisture_content"],
        }],
        gates=[{
            "key": "timber_moisture_content",
            "threshold": {"min": 7, "max": 8, "unit": "%"},
        }],
    )
    assert published["current_version"] == 2

    after = await _create_project(
        client_client, "Started on v2", configuration_id=clone["id"]
    )
    assert before["config_version"] == 1
    assert after["config_version"] == 2

    # v1 is untouched — the running project's stage 1 has neither the new document
    # nor the new gate
    v1 = repo.ConfigScope(ObjectId(clone["id"]), 1, "sequential")
    v2 = repo.ConfigScope(ObjectId(clone["id"]), 2, "sequential")
    old_stage = await repo.stage_def_by_key(db, "project_initiation", v1)
    new_stage = await repo.stage_def_by_key(db, "project_initiation", v2)
    assert old_stage["quality_gates"] == []
    assert new_stage["quality_gates"] == ["timber_moisture_content"]

    old_docs = {g["key"] for g in old_stage["entry_gates"] if g["type"] == "document"}
    new_docs = {g["key"] for g in new_stage["entry_gates"] if g["type"] == "document"}
    assert "insurance_certificate" not in old_docs
    assert "insurance_certificate" in new_docs

    # the retuned threshold lives only in v2 (G-3, G-5)
    assert (await repo.gate_rule(db, "timber_moisture_content", v1))["threshold"]["max"] == 9
    assert (await repo.gate_rule(db, "timber_moisture_content", v2))["threshold"]["max"] == 8

    # and the engine agrees: only the newer project waits on the added document
    async def _waiting_on(project):
        res = await client_client.get(f"{BASE}/{project['id']}/stages/1")
        return res.json()["data"]["evaluation"]["waiting_on"]

    assert "doc:insurance_certificate" not in await _waiting_on(before)
    assert "doc:insurance_certificate" in await _waiting_on(after)


async def test_publish_carries_over_stages_the_payload_omits(
    client_client, onboarded_company
):
    """A publish is the full edited set, but a stage nobody touched must survive
    intact — dependency edges included, since those encode the workflow shape."""
    db = _tenant_db(onboarded_company)
    clone = await _clone(client_client)
    await _publish(client_client, clone["id"], stages=[{
        "key": "project_initiation", "entry_documents": [], "quality_gates": [],
    }])

    v2 = repo.ConfigScope(ObjectId(clone["id"]), 2, "sequential")
    stages = {s["key"]: s for s in await repo.stage_defs(db, v2)}
    assert len(stages) == 9

    untouched = stages["material_procurement"]
    assert untouched["approver_role"] == "procurement_manager"
    deps = [g["depends_on"] for g in untouched["entry_gates"]
            if g["type"] == "dependency"]
    assert deps == ["measurement_verification"]        # the chain is intact


async def test_publish_can_change_the_workflow_shape(client_client, onboarded_company):
    db = _tenant_db(onboarded_company)
    clone = await _clone(client_client)
    published = await _publish(client_client, clone["id"], workflow_shape="concurrent")

    assert published["workflow_shape"] == "concurrent"
    v2 = repo.ConfigScope(ObjectId(clone["id"]), 2, "concurrent")
    stages = {s["order"]: s for s in await repo.stage_defs(db, v2)}

    def _deps(stage):
        return [g["depends_on"] for g in stage["entry_gates"]
                if g.get("type") == "dependency"]

    assert _deps(stages[5]) == ["project_initiation"]          # fans off stage 1
    assert set(_deps(stages[9])) == {stages[o]["key"] for o in range(2, 9)}


async def test_publish_rejects_stages_outside_the_fixed_skeleton(client_client):
    """D2/G-2 — a configuration tunes the 9 stages; it cannot invent one, because
    module integrations hook stage keys."""
    clone = await _clone(client_client)
    res = await client_client.post(f"{CONFIGS}/{clone['id']}/versions", json={
        "stages": [{"key": "custom_stage", "entry_documents": [],
                    "quality_gates": []}],
    })
    assert res.status_code == 422, res.text
    assert "custom_stage" in res.json()["error"]["message"]


async def test_publish_rejects_gates_not_in_the_catalog(client_client):
    clone = await _clone(client_client)
    res = await client_client.post(f"{CONFIGS}/{clone['id']}/versions", json={
        "stages": [{"key": "site_survey", "entry_documents": [],
                    "quality_gates": ["not_a_real_gate"]}],
    })
    assert res.status_code == 422, res.text
    assert "not_a_real_gate" in res.json()["error"]["message"]


# --- rename / default / activate / delete -------------------------------------

async def test_rename_and_set_default(client_client, onboarded_company):
    clone = await _clone(client_client)
    res = await client_client.patch(
        f"{CONFIGS}/{clone['id']}", json={"name": "Renamed", "is_default": True}
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"]["name"] == "Renamed"

    # exactly one default (G-4): Standard was demoted
    configs = await _configs(client_client)
    assert [c["name"] for c in configs.values() if c["is_default"]] == ["Renamed"]

    # and a project with no configuration_id now lands on the new default
    project = await _create_project(client_client, "Follows the default")
    assert project["configuration_id"] == clone["id"]


async def test_the_default_cannot_be_cleared_or_deactivated(client_client):
    configs = await _configs(client_client)
    standard = configs["Standard"]

    for body in ({"is_default": False}, {"is_active": False}):
        res = await client_client.patch(f"{CONFIGS}/{standard['id']}", json=body)
        assert res.status_code == 422, res.text


async def test_deactivated_configuration_leaves_existing_projects_alone(
    client_client, onboarded_company
):
    """Deactivating is the safe alternative to deleting — it stops NEW projects
    without disturbing the ones already running on it."""
    clone = await _clone(client_client)
    project = await _create_project(
        client_client, "On a retired config", configuration_id=clone["id"]
    )

    res = await client_client.patch(f"{CONFIGS}/{clone['id']}", json={"is_active": False})
    assert res.status_code == 200, res.text

    # new projects can't choose it any more...
    blocked = await client_client.post(
        BASE, json={"name": "Too late", "configuration_id": clone["id"]}
    )
    assert blocked.status_code == 422, blocked.text

    # ...but the running one still resolves its 9 stages
    timeline = await client_client.get(f"{BASE}/{project['id']}/timeline")
    assert timeline.status_code == 200
    assert len(timeline.json()["data"]["stages"]) == 9

    # and it is hidden from the Stage-1 picker
    picker = await client_client.get(f"{CONFIGS}?active_only=true")
    assert clone["id"] not in [c["id"] for c in picker.json()["data"]]


async def test_delete_is_guarded(client_client, onboarded_company):
    """G-4 — a system config is never deletable, and neither is one a live project
    pins (that would strand the project's stage machine)."""
    configs = await _configs(client_client)
    res = await client_client.delete(f"{CONFIGS}/{configs['Concurrent']['id']}")
    assert res.status_code == 422, res.text
    assert "built-in" in res.json()["error"]["message"]

    clone = await _clone(client_client)
    await _create_project(client_client, "Pins it", configuration_id=clone["id"])
    res = await client_client.delete(f"{CONFIGS}/{clone['id']}")
    assert res.status_code == 422, res.text
    assert "deactivate" in res.json()["error"]["message"]


async def test_unpinned_configuration_can_be_deleted(client_client):
    clone = await _clone(client_client, name="Never used")
    res = await client_client.delete(f"{CONFIGS}/{clone['id']}")
    assert res.status_code == 204, res.text
    assert "Never used" not in await _configs(client_client)


# --- gate catalog --------------------------------------------------------------

async def test_catalog_seeds_the_builtin_gates(client_client):
    res = await client_client.get(CATALOG)
    assert res.status_code == 200, res.text
    entries = {g["key"]: g for g in res.json()["data"]}

    assert len(entries) == 8
    assert all(g["is_builtin"] for g in entries.values())
    assert entries["timber_moisture_content"]["name"] == "Timber moisture content"


async def test_custom_gate_can_be_created_and_attached(
    client_client, onboarded_company
):
    """The gap this feature closes: adding a gate to a stage is now a config edit,
    not a seed change."""
    db = _tenant_db(onboarded_company)
    res = await client_client.post(CATALOG, json={
        "key": "adhesive_open_time", "name": "Adhesive open time",
        "type": "measurement", "threshold": {"max_minutes": 20},
    })
    assert res.status_code == 201, res.text

    clone = await _clone(client_client)
    await _publish(client_client, clone["id"], stages=[{
        "key": "installation", "entry_documents": [],
        "quality_gates": ["adhesive_open_time"],
    }])

    v2 = repo.ConfigScope(ObjectId(clone["id"]), 2, "sequential")
    stage = await repo.stage_def_by_key(db, "installation", v2)
    assert stage["quality_gates"] == ["adhesive_open_time"]
    # copy-on-attach: the tuned rule lives in the config version (G-3)
    rule = await repo.gate_rule(db, "adhesive_open_time", v2)
    assert rule["threshold"] == {"max_minutes": 20}


async def test_custom_gate_validation_and_duplicate_keys(client_client):
    # a measurement gate needs a threshold; an inspection gate needs a checklist
    res = await client_client.post(CATALOG, json={
        "key": "no_criterion", "name": "No criterion", "type": "measurement",
    })
    assert res.status_code == 422, res.text

    body = {"key": "dupe", "name": "Dupe", "type": "inspection",
            "checklist": ["one"]}
    assert (await client_client.post(CATALOG, json=body)).status_code == 201
    assert (await client_client.post(CATALOG, json=body)).status_code == 422


async def test_builtin_gates_cannot_be_deleted(client_client):
    res = await client_client.delete(f"{CATALOG}/timber_moisture_content")
    assert res.status_code == 422, res.text
    assert "built-in" in res.json()["error"]["message"]


async def test_deleting_a_custom_gate_leaves_published_versions_working(
    client_client, onboarded_company
):
    """Copy-on-attach means a published version owns its rules — removing the
    catalog entry must not disarm a running project's gate (G-3)."""
    db = _tenant_db(onboarded_company)
    await client_client.post(CATALOG, json={
        "key": "site_noise_limit", "name": "Site noise limit",
        "type": "measurement", "threshold": {"max_db": 85},
    })
    clone = await _clone(client_client)
    await _publish(client_client, clone["id"], stages=[{
        "key": "installation", "entry_documents": [],
        "quality_gates": ["site_noise_limit"],
    }])

    assert (await client_client.delete(f"{CATALOG}/site_noise_limit")).status_code == 204

    v2 = repo.ConfigScope(ObjectId(clone["id"]), 2, "sequential")
    assert (await repo.gate_rule(db, "site_noise_limit", v2))["threshold"] == {"max_db": 85}


# --- RBAC (§4) -----------------------------------------------------------------

async def test_managing_configurations_requires_settings_write(
    client_client, onboarded_company
):
    """§4 — reading the picker is `projects` READ, but building configurations is
    `settings` WRITE, exactly like the approver-role map it sits beside."""
    db = _tenant_db(onboarded_company)
    await db.roles.update_one({"name": "Owner"}, {"$set": {"permissions.settings": 2}})

    # the Stage-1 picker still works without Settings access
    assert (await client_client.get(CONFIGS)).status_code == 200

    assert (await client_client.post(CONFIGS, json={"name": "Nope"})).status_code == 403
    assert (await client_client.get(CATALOG)).status_code == 403

    await db.roles.update_one({"name": "Owner"}, {"$set": {"permissions.projects": 0}})
    assert (await client_client.get(CONFIGS)).status_code == 403


async def test_configuration_writes_are_audited(client_client, onboarded_company):
    db = _tenant_db(onboarded_company)
    clone = await _clone(client_client, name="Audited")
    await _publish(client_client, clone["id"])
    await client_client.patch(f"{CONFIGS}/{clone['id']}", json={"name": "Audited v2"})

    actions = [
        a["action"] async for a in db.activity_log.find({"module": "projects"})
    ]
    for expected in (
        "projects.configuration_created",
        "projects.configuration_published",
        "projects.configuration_updated",
    ):
        assert expected in actions
