"""Provisioning engine (docs/MULTITENANCY.md §3).

Idempotent, resumable jobs. Every step is safe to re-run: seeds use
create_index (no-op if exists) + $setOnInsert upserts, so resuming a failed
job completes without duplicating data.

Provision sequence: reserve → create_db → seed_modules → seed_rbac →
create_owner_user → seed_settings → finalize.
Teardown: drop_db → finalize (suspend or hard-remove). Teardown's dropDatabase
is the ONLY place a full DB is dropped.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from bson import ObjectId

from app.control_plane.companies import repository as companies_repo
from app.control_plane.companies.models import OnboardCompanyPayload
from app.control_plane.provisioning import models as jobs
from app.control_plane.provisioning.registry import seed_enabled_modules
from app.core.audit import write_admin_audit
from app.core.db import get_db_manager
from app.core.errors import PROVISIONING_FAILED, VALIDATION_ERROR, DomainError
from app.core.security import hash_password
from app.modules.settings.seed import seed_company_profile, seed_default_roles


class ProvisionResult:
    def __init__(self, company: dict, job: dict, owner_temp_password: str | None):
        self.company = company
        self.job = job
        # Only set when the owner user was newly created in THIS run; it is
        # never persisted anywhere.
        self.owner_temp_password = owner_temp_password


async def onboard_company(
    payload: OnboardCompanyPayload, actor_id: str = "system"
) -> ProvisionResult:
    """Admin "onboard company" action: reserve the registry doc, create the
    tracked job, and run it to completion (docs/ADMIN_PORTAL.md §1)."""
    control = get_db_manager().control
    await companies_repo.ensure_company_indexes(control)
    await jobs.ensure_job_indexes(control)

    if await companies_repo.get_by_slug(control, payload.slug):
        raise DomainError(
            VALIDATION_ERROR,
            f"Company slug '{payload.slug}' already exists.",
            http_status=409,
            details={"slug": payload.slug},
        )

    company = await companies_repo.reserve(control, payload, onboarded_by=actor_id)
    job = await jobs.create_job(control, company["_id"], "provision")
    return await run_provision_job(job["_id"], payload=payload, actor_id=actor_id)


async def run_provision_job(
    job_id: ObjectId | str,
    payload: OnboardCompanyPayload | None = None,
    actor_id: str = "system",
) -> ProvisionResult:
    """Run (or RESUME) a provisioning job from its first non-done step.

    `payload` is required only for the create_owner_user / seed_settings steps
    of a fresh run; resuming past those steps works without it.
    """
    dbm = get_db_manager()
    control = dbm.control

    job = await jobs.get_job(control, job_id)
    if job is None:
        raise DomainError("TENANT_NOT_FOUND", "Provisioning job not found.", 404)
    company = await companies_repo.get_by_id(control, job["company_id"])
    if company is None:
        raise DomainError("TENANT_NOT_FOUND", "Company for job not found.", 404)

    tenant_db = dbm.tenant(company["db_name"])
    owner_temp_password: str | None = None

    await jobs.set_job_state(control, job["_id"], "running")

    for step in job["steps"]:
        if step["status"] == "done":
            continue  # resume: skip completed steps
        name = step["name"]
        await jobs.set_step_status(control, job["_id"], name, "running")
        try:
            if name == "create_db":
                # Mongo creates lazily on first write — touch the tenant DB.
                await tenant_db.tenant_meta.update_one(
                    {"_id": "meta"},
                    {"$setOnInsert": {
                        "slug": company["slug"],
                        "db_name": company["db_name"],
                        "created_at": datetime.now(UTC),
                    }},
                    upsert=True,
                )

            elif name == "seed_modules":
                await seed_enabled_modules(tenant_db, company["enabled_modules"])
                await jobs.set_job_state(control, job["_id"], "seeded")

            elif name == "seed_rbac":
                await seed_default_roles(tenant_db)

            elif name == "create_owner_user":
                if payload is None:
                    raise RuntimeError(
                        "create_owner_user requires the onboarding payload"
                    )
                owner_temp_password = await _create_owner_user(
                    control, tenant_db, company, payload
                )

            elif name == "seed_settings":
                if payload is None:
                    raise RuntimeError("seed_settings requires the onboarding payload")
                await seed_company_profile(tenant_db, {
                    "name": company["name"],
                    "contact": {"email": payload.owner.email},
                })

            elif name == "finalize":
                await companies_repo.update_fields(control, company["_id"], {
                    "status": "active",
                    "provisioned_at": datetime.now(UTC),
                })
                await jobs.set_job_state(control, job["_id"], "done", finished=True)
                await write_admin_audit(
                    actor_id=actor_id,
                    action="company.onboarded",
                    target={"type": "company", "id": str(company["_id"]),
                            "slug": company["slug"]},
                    details={"db_name": company["db_name"],
                             "enabled_modules": company["enabled_modules"]},
                )

            else:  # unknown step — treat as failure, never silently skip
                raise RuntimeError(f"unknown provisioning step: {name}")

            await jobs.set_step_status(control, job["_id"], name, "done")

        except Exception as exc:
            await jobs.set_step_status(control, job["_id"], name, "failed")
            await jobs.set_job_state(control, job["_id"], "failed", error=str(exc))
            await companies_repo.update_fields(
                control, company["_id"], {"status": "failed"}
            )
            raise DomainError(
                PROVISIONING_FAILED,
                f"Provisioning failed at step '{name}': {exc}",
                http_status=500,
                details={"job_id": str(job["_id"]), "step": name},
            ) from exc

    final_job = await jobs.get_job(control, job["_id"])
    final_company = await companies_repo.get_by_id(control, company["_id"])
    assert final_job is not None and final_company is not None  # just written
    return ProvisionResult(final_company, final_job, owner_temp_password)


async def _create_owner_user(
    control, tenant_db, company: dict, payload: OnboardCompanyPayload
) -> str | None:
    """Create the first employee (client-side admin) with the Owner role and a
    generated temp password; must_reset_password forces a change on first
    login. Idempotent: upsert by email; seats_used only increments on insert."""
    role_ids = await seed_default_roles(tenant_db)  # idempotent; gets Owner id
    temp_password = secrets.token_urlsafe(12)
    now = datetime.now(UTC)
    result = await tenant_db.users.update_one(
        {"email": payload.owner.email},
        {"$setOnInsert": {
            "email": payload.owner.email,
            "password_hash": hash_password(temp_password),
            "name": payload.owner.name,
            "role_id": role_ids["Owner"],
            "is_blocked": False,
            "failed_attempts": 0,
            "locked_until": None,
            "must_reset_password": True,
            "last_login_at": None,
            "created_at": now,
            "updated_at": now,
        }},
        upsert=True,
    )
    await tenant_db.users.create_index("email", unique=True)
    if result.upserted_id is not None:
        await companies_repo.inc_seats_used(control, company["_id"], 1)
        return temp_password
    return None  # owner already existed (resumed run) — no new password


async def teardown_company(
    company_id: ObjectId | str, hard: bool = False, actor_id: str = "system"
) -> dict:
    """Offboarding: drop the tenant DB, then suspend or hard-remove the company
    doc. Removes ONLY that company's data (docs/MULTITENANCY.md §3, §7)."""
    dbm = get_db_manager()
    control = dbm.control

    company = await companies_repo.get_by_id(control, company_id)
    if company is None:
        raise DomainError("TENANT_NOT_FOUND", "Company not found.", 404)

    job = await jobs.create_job(control, company["_id"], "teardown")
    await jobs.set_job_state(control, job["_id"], "running")
    try:
        await jobs.set_step_status(control, job["_id"], "drop_db", "running")
        await dbm.raw_client().drop_database(company["db_name"])
        await jobs.set_step_status(control, job["_id"], "drop_db", "done")

        await jobs.set_step_status(control, job["_id"], "finalize", "running")
        if hard:
            await companies_repo.delete(control, company["_id"])
        else:
            await companies_repo.update_fields(
                control, company["_id"], {"status": "suspended"}
            )
        await jobs.set_step_status(control, job["_id"], "finalize", "done")
        await jobs.set_job_state(control, job["_id"], "done", finished=True)
        await write_admin_audit(
            actor_id=actor_id,
            action="company.removed" if hard else "company.suspended",
            target={"type": "company", "id": str(company["_id"]),
                    "slug": company["slug"]},
            details={"db_name": company["db_name"], "hard": hard},
        )
    except Exception as exc:
        await jobs.set_job_state(control, job["_id"], "failed", error=str(exc))
        raise DomainError(
            PROVISIONING_FAILED, f"Teardown failed: {exc}", 500,
            details={"job_id": str(job["_id"])},
        ) from exc

    final_job = await jobs.get_job(control, job["_id"])
    assert final_job is not None  # just written
    return final_job
