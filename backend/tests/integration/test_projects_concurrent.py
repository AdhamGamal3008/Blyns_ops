"""Concurrent (parallel-stage) workflow (docs/CONCURRENT_WORKFLOW_PLAN.md).

Phase 0 — the data foundation: a tenant seeds BOTH stage templates; the
'sequential' one is today's linear chain (unchanged), and the derived 'concurrent'
one runs stages 2-8 off stage 1 with stage 9 waiting on all of them. The engine
that acts on this (parallel unlock, completion) lands in Phase 1.
"""

from __future__ import annotations

from app.core.db import get_db_manager
from app.modules.projects import repository as repo
from app.modules.projects import seed as projects_seed
from tests.integration.test_projects import _advance, _create_project

BASE = "/api/v1/projects"


def _tenant_db(onboarded_company):
    return get_db_manager().tenant(onboarded_company["company"]["db_name"])


async def test_both_templates_seed_with_the_same_stages(onboarded_company):
    db = _tenant_db(onboarded_company)
    seq = await repo.stage_defs(db)                       # default = sequential
    con = await repo.stage_defs(db, "concurrent")

    assert len(seq) == 9 and len(con) == 9               # not 18 — helper scopes by type
    assert [d["key"] for d in seq] == [d["key"] for d in con]      # same stages
    assert all(d["workflow_type"] == "sequential" for d in seq)
    assert all(d["workflow_type"] == "concurrent" for d in con)


async def test_sequential_is_a_linear_chain_with_stage4_dependency(onboarded_company):
    db = _tenant_db(onboarded_company)
    seq = {d["order"]: d for d in await repo.stage_defs(db)}

    # every stage 2..9 declares a blocking dependency (the chain is fully explicit,
    # so it survives Phase 1 dropping the hard-coded linear loop)
    for order in range(2, 10):
        deps = [g["depends_on"] for g in seq[order]["entry_gates"]
                if g.get("type") == "dependency"]
        assert deps, f"sequential stage {order} has no declared dependency"

    # stage 4 now depends on design_package (it relied on the loop before)
    s4_deps = [g["depends_on"] for g in seq[4]["entry_gates"]
               if g.get("type") == "dependency"]
    assert "design_package" in s4_deps


async def test_concurrent_runs_2to8_off_stage1_and_9_waits_for_all(onboarded_company):
    db = _tenant_db(onboarded_company)
    con = {d["order"]: d for d in await repo.stage_defs(db, "concurrent")}
    first_key = con[1]["key"]

    def deps(order: int) -> set[str]:
        return {g["depends_on"] for g in con[order]["entry_gates"]
                if g.get("type") == "dependency"}

    assert deps(1) == set()                              # stage 1: no dependency
    for order in range(2, 9):                            # 2..8 depend only on stage 1
        assert deps(order) == {first_key}
    middle = {con[o]["key"] for o in range(2, 9)}
    assert deps(9) == middle                             # stage 9 waits for all of 2..8


async def test_key_lookups_scope_to_type_and_seed_is_idempotent(onboarded_company):
    db = _tenant_db(onboarded_company)
    # key lookups return the right template's copy
    assert (await repo.stage_def_by_key(db, "factory_release"))["workflow_type"] == "sequential"
    assert (await repo.stage_def_by_key(
        db, "factory_release", "concurrent"))["workflow_type"] == "concurrent"

    # re-running the seed never duplicates or clobbers
    await projects_seed.seed(db)
    assert await db.stage_definitions.count_documents({"workflow_type": "sequential"}) == 9
    assert await db.stage_definitions.count_documents({"workflow_type": "concurrent"}) == 9


# --- Phase 1: the engine acts on the concurrent template ---------------------

async def test_concurrent_stage1_opens_2to8_in_parallel(client_client):
    project = await _create_project(
        client_client, name="Parallel build", workflow_type="concurrent"
    )
    pid = project["id"]
    assert project["workflow_type"] == "concurrent"          # persisted at creation

    # walk stage 1 (project_initiation) to approved — identical to sequential
    body = await _advance(client_client, pid, 1)

    # the single approval opened EVERY one of stages 2..8 at once
    assert sorted(s["order"] for s in body["next_stages"]) == [2, 3, 4, 5, 6, 7, 8]

    # the timeline confirms 2..8 are entered and 9 (Handover) waits for all of them
    tl = (await client_client.get(f"{BASE}/{pid}/timeline")).json()["data"]
    assert tl["workflow_type"] == "concurrent"
    by_order = {s["order"]: s for s in tl["stages"]}
    for order in range(2, 9):
        assert by_order[order]["entered_at"] is not None, f"stage {order} not entered"
    assert by_order[9]["entered_at"] is None                 # not unlocked yet
    assert 9 not in {s["order"] for s in body["next_stages"]}

    # the representative cursor points at the lowest stage still in flight
    proj = (await client_client.get(f"{BASE}/{pid}")).json()["data"]
    assert proj["current_stage_order"] == 2


async def test_sequential_project_still_advances_one_stage_at_a_time(client_client):
    """The same engine, driven by the sequential template, opens exactly one next
    stage — the built-in regression that the DAG change didn't leak into linear."""
    project = await _create_project(client_client, name="Linear build")  # default
    pid = project["id"]
    assert project["workflow_type"] == "sequential"

    body = await _advance(client_client, pid, 1)
    assert [s["order"] for s in body["next_stages"]] == [2]  # only the next
    assert body["next_stage"]["order"] == 2

    tl = (await client_client.get(f"{BASE}/{pid}/timeline")).json()["data"]
    by_order = {s["order"]: s for s in tl["stages"]}
    assert by_order[2]["entered_at"] is not None
    assert by_order[3]["entered_at"] is None                 # stage 3 stays closed
