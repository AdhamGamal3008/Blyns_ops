"""Multitenancy & provisioning must-haves (docs/TESTING.md §3)."""

from __future__ import annotations

import pytest

from app.control_plane.companies.models import (
    OnboardCompanyPayload,
    OwnerPayload,
)
from app.control_plane.provisioning import registry
from app.control_plane.provisioning.engine import (
    onboard_company,
    run_provision_job,
    teardown_company,
)
from app.core.db import close_db_manager, init_db_manager
from app.core.errors import DomainError
from app.core.security import verify_password


@pytest.fixture
async def engine_db(mongo_uri):
    """The engine uses the process-global DBManager."""
    manager = init_db_manager(mongo_uri)
    yield manager
    close_db_manager()


def payload(slug: str, modules: list[str] | None = None) -> OnboardCompanyPayload:
    return OnboardCompanyPayload(
        name=f"{slug.title()} Corp",
        slug=slug,
        seat_limit=10,
        enabled_modules=modules
        or ["dashboard", "settings", "projects", "crm", "inventory", "finance"],
        owner=OwnerPayload(name="Jane Doe", email=f"jane@{slug}.com"),
    )


async def test_onboarding_creates_seeded_tenant_db(engine_db):
    dbs_before = await engine_db.raw_client().list_database_names()
    assert "test_tenant_acme1" not in dbs_before

    result = await onboard_company(payload("acme1"), actor_id="admin-test")
    company, job = result.company, result.job

    # company registry finalized
    assert company["status"] == "active"
    assert company["db_name"] == "test_tenant_acme1"
    assert company["provisioned_at"] is not None
    assert company["seats_used"] == 1

    # job done, every step done
    assert job["state"] == "done"
    assert all(s["status"] == "done" for s in job["steps"])
    assert job["finished_at"] is not None

    # a NEW database exists that did not exist before (acceptance §7)
    dbs_after = await engine_db.raw_client().list_database_names()
    assert "test_tenant_acme1" in dbs_after

    t = engine_db.tenant("test_tenant_acme1")
    # the projects seed ran: the 9-stage machine in BOTH templates (sequential +
    # concurrent, docs/CONCURRENT_WORKFLOW_PLAN.md) + gates etc.
    assert await t.stage_definitions.count_documents({}) == 18
    assert await t.stage_definitions.count_documents({"workflow_type": "sequential"}) == 9
    assert await t.gate_rules.count_documents({}) == 8
    assert await t.report_types.count_documents({}) == 8
    assert await t.approver_role_map.count_documents({}) == 6
    # other module seeds
    assert await t.roles.count_documents({}) == 4          # Owner/Manager/Member/Viewer
    assert await t.pipelines.count_documents({"key": "default"}) == 1
    assert await t.warehouses.count_documents({"code": "WH1"}) == 1
    assert await t.accounts.count_documents({}) == 8       # starter chart
    assert await t.counters.count_documents({}) == 2       # invoice + bill
    assert await t.company_profile.count_documents({"_id": "company_profile"}) == 1

    # one Owner user with hashed temp password + forced reset
    owner = await t.users.find_one({"email": "jane@acme1.com"})
    assert owner is not None
    assert owner["must_reset_password"] is True
    owner_role = await t.roles.find_one({"_id": owner["role_id"]})
    assert owner_role["name"] == "Owner"
    assert result.owner_temp_password is not None
    assert verify_password(result.owner_temp_password, owner["password_hash"])

    # admin audit written (CLAUDE.md rule 4)
    audit = await engine_db.control.admin_audit_log.find_one(
        {"action": "company.onboarded", "target.slug": "acme1"}
    )
    assert audit is not None and audit["actor_id"] == "admin-test"


async def test_only_enabled_modules_are_seeded(engine_db):
    await onboard_company(payload("acme2", modules=["dashboard", "settings", "crm"]))
    t = engine_db.tenant("test_tenant_acme2")
    assert await t.pipelines.count_documents({}) == 1       # crm seeded
    assert await t.stage_definitions.count_documents({}) == 0  # projects NOT enabled
    assert await t.warehouses.count_documents({}) == 0         # inventory NOT enabled


async def test_duplicate_slug_rejected(engine_db):
    await onboard_company(payload("acme3"))
    with pytest.raises(DomainError) as exc:
        await onboard_company(payload("acme3"))
    assert exc.value.code == "VALIDATION_ERROR"
    assert exc.value.http_status == 409


async def test_failed_job_resumes_idempotently(engine_db, monkeypatch):
    """Re-running a failed provisioning job completes without duplicating data."""
    real_seed = registry.MODULE_SEEDS["finance"]
    calls = {"n": 0}

    async def flaky_finance_seed(tenant_db):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated seed crash")
        await real_seed(tenant_db)

    monkeypatch.setitem(registry.MODULE_SEEDS, "finance", flaky_finance_seed)

    with pytest.raises(DomainError) as exc:
        await onboard_company(payload("acme4"))
    assert exc.value.code == "PROVISIONING_FAILED"
    job_id = exc.value.details["job_id"]

    # failure captured: job failed at seed_modules, company failed
    job = await engine_db.control.provisioning_jobs.find_one(
        {"company_id": (await engine_db.control.companies.find_one({"slug": "acme4"}))["_id"]}
    )
    assert job["state"] == "failed"
    assert "simulated seed crash" in job["error"]
    company = await engine_db.control.companies.find_one({"slug": "acme4"})
    assert company["status"] == "failed"

    # resume: completes from the first non-done step, no duplicate seeds
    result = await run_provision_job(job_id, payload=payload("acme4"))
    assert result.job["state"] == "done"
    assert result.company["status"] == "active"
    assert result.company["seats_used"] == 1  # not double-incremented

    t = engine_db.tenant("test_tenant_acme4")
    assert await t.stage_definitions.count_documents({}) == 18  # 9 seq + 9 concurrent, idempotent
    assert await t.roles.count_documents({}) == 4
    assert await t.accounts.count_documents({}) == 8
    assert await t.users.count_documents({}) == 1


async def test_teardown_drops_only_target_tenant(engine_db):
    await onboard_company(payload("acme5"))
    await onboard_company(payload("acme6"))

    company5 = await engine_db.control.companies.find_one({"slug": "acme5"})
    job = await teardown_company(company5["_id"], hard=False)
    assert job["state"] == "done"

    dbs = await engine_db.raw_client().list_database_names()
    assert "test_tenant_acme5" not in dbs      # target dropped
    assert "test_tenant_acme6" in dbs          # neighbor intact
    other = engine_db.tenant("test_tenant_acme6")
    assert await other.stage_definitions.count_documents({}) == 18  # neighbor intact

    # control plane intact; company suspended, not removed (soft teardown)
    company5 = await engine_db.control.companies.find_one({"slug": "acme5"})
    assert company5["status"] == "suspended"


async def test_hard_teardown_removes_company_doc(engine_db):
    await onboard_company(payload("acme7"))
    company = await engine_db.control.companies.find_one({"slug": "acme7"})
    await teardown_company(company["_id"], hard=True)
    assert await engine_db.control.companies.find_one({"slug": "acme7"}) is None
    assert "test_tenant_acme7" not in await engine_db.raw_client().list_database_names()
