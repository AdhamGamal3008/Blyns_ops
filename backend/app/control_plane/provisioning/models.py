"""Provisioning job document shapes (docs/MULTITENANCY.md §3).

A job is idempotent and resumable: re-running resumes from the first
non-`done` step. Step statuses: pending | running | done | failed.
Job states: pending | running | seeded | done | failed.

`build_indexes` from the spec's example job folds into `seed_modules`: the
module seeding contract (§5) has each module's seed() create its own
collections AND indexes in one idempotent call.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

JobType = Literal["provision", "teardown"]

PROVISION_STEPS: list[str] = [
    "create_db",
    "seed_modules",      # per-module collections + indexes + defaults (§5)
    "seed_rbac",         # default client roles Owner/Manager/Member/Viewer
    "create_owner_user", # first employee, temp password, seats_used += 1
    "seed_settings",     # company profile + calendar defaults
    "finalize",          # company active, provisioned_at, admin audit
]

TEARDOWN_STEPS: list[str] = [
    "drop_db",
    "finalize",
]


async def ensure_job_indexes(control_db: AsyncIOMotorDatabase) -> None:
    await control_db.provisioning_jobs.create_index("company_id")
    await control_db.provisioning_jobs.create_index("state")


async def create_job(
    control_db: AsyncIOMotorDatabase,
    company_id: ObjectId,
    job_type: JobType,
) -> dict:
    steps = PROVISION_STEPS if job_type == "provision" else TEARDOWN_STEPS
    doc = {
        "company_id": company_id,
        "type": job_type,
        "state": "pending",
        "steps": [{"name": name, "status": "pending"} for name in steps],
        "error": None,
        "created_at": datetime.now(UTC),
        "finished_at": None,
    }
    result = await control_db.provisioning_jobs.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def get_job(control_db: AsyncIOMotorDatabase, job_id: ObjectId | str) -> dict | None:
    return await control_db.provisioning_jobs.find_one({"_id": ObjectId(job_id)})


async def set_step_status(
    control_db: AsyncIOMotorDatabase, job_id: ObjectId, step: str, status: str
) -> None:
    await control_db.provisioning_jobs.update_one(
        {"_id": job_id, "steps.name": step},
        {"$set": {"steps.$.status": status}},
    )


async def set_job_state(
    control_db: AsyncIOMotorDatabase,
    job_id: ObjectId,
    state: str,
    error: str | None = None,
    finished: bool = False,
) -> None:
    fields: dict = {"state": state, "error": error}
    if finished:
        fields["finished_at"] = datetime.now(UTC)
    await control_db.provisioning_jobs.update_one({"_id": job_id}, {"$set": fields})
