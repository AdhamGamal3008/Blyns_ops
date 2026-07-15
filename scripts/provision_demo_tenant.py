"""Onboard the "acme" demo company end-to-end (docs/ENVIRONMENTS.md §2).

Run from backend/ so .env is picked up:  python ../scripts/provision_demo_tenant.py
Prints the Owner's temp password (must_reset_password forces a change on
first login — the password is never persisted anywhere).
"""

from __future__ import annotations

import asyncio

from app.control_plane.companies.models import (
    OnboardCompanyPayload,
    OwnerPayload,
    SecurityPolicy,
)
from app.control_plane.provisioning.engine import onboard_company
from app.core.config import settings
from app.core.db import close_db_manager, init_db_manager
from app.core.errors import DomainError

PAYLOAD = OnboardCompanyPayload(
    name="Acme Corp",
    slug="acme",
    seat_limit=25,
    enabled_modules=["dashboard", "settings", "projects", "crm", "inventory", "finance"],
    owner=OwnerPayload(name="Jane Doe", email="jane@acme.com"),
    security=SecurityPolicy(failed_login_threshold=5, lockout_minutes=15),
)


async def main() -> None:
    init_db_manager(settings.mongo_uri)
    try:
        result = await onboard_company(PAYLOAD, actor_id="system:demo-script")
        company, job = result.company, result.job
        print(f"company : {company['name']} (slug={company['slug']})")
        print(f"status  : {company['status']}")
        print(f"db_name : {company['db_name']}")
        print(f"modules : {', '.join(company['enabled_modules'])}")
        done = sum(1 for s in job["steps"] if s["status"] == "done")
        print(f"job     : {job['state']} ({done}/{len(job['steps'])} steps done)")
        print(f"owner   : {PAYLOAD.owner.email}")
        if result.owner_temp_password:
            print(f"temp pw : {result.owner_temp_password}  (reset forced on first login)")
        else:
            print("temp pw : unchanged (owner already existed)")
    except DomainError as exc:
        if exc.code == "VALIDATION_ERROR":
            print(f"already onboarded: {exc.message}")
        else:
            raise
    finally:
        close_db_manager()


if __name__ == "__main__":
    asyncio.run(main())
