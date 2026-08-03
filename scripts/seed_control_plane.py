"""Seed the control plane: default admin roles + first Super Admin
(docs/AUTH_RBAC.md §2, docs/ENVIRONMENTS.md §2). Idempotent.

Run from backend/ so .env is picked up:
    python ../scripts/seed_control_plane.py [--email a@b.c] [--name "Jane"] [--password ...]

Without --password a random one is generated and printed ONCE (never stored
in plaintext).
"""

from __future__ import annotations

import argparse
import asyncio
import secrets

from app.control_plane.admin_users.repository import (
    create_admin_user,
    ensure_admin_indexes,
    seed_admin_roles,
)
from app.control_plane.ip_access.repository import ensure_ip_rule_indexes
from app.control_plane.ip_access.seed import seed_ip_access_rules
from app.core.audit import write_admin_audit
from app.core.config import settings
from app.core.db import close_db_manager, init_db_manager
from app.core.rate_limit import ensure_bucket_indexes, ensure_enforcement_indexes
from app.core.security import hash_password


async def main(email: str, name: str, password: str | None) -> None:
    init_db_manager(settings.mongo_uri)
    try:
        control = init_db_manager(settings.mongo_uri).control
        await ensure_admin_indexes(control)
        await ensure_bucket_indexes(control)
        await ensure_enforcement_indexes(control)
        await ensure_ip_rule_indexes(control)
        role_ids = await seed_admin_roles(control)
        print(f"admin roles : {', '.join(role_ids)}")

        # Production-only IP access seed (country denylist + admin allowlist).
        # Ships empty and no-ops outside production (docs/IP_ACCESS_CONTROL_PLAN.md P6).
        seeded = await seed_ip_access_rules(control, settings)
        summary = ", ".join(f"{r['kind']} {r['match_type']} {r['value']}" for r in seeded)
        print(f"ip rules    : {len(seeded)} seeded ({settings.env})"
              + (f" — {summary}" if summary else ""))

        generated = password is None
        password = password or secrets.token_urlsafe(12)
        created = await create_admin_user(
            control, email=email, name=name,
            password_hash=hash_password(password),
            role_id=role_ids["Super Admin"],
        )
        if created is None:
            print(f"super admin : {email} already exists (unchanged)")
        else:
            await write_admin_audit(
                actor_id="system:seed-script",
                action="admin_user.created",
                target={"type": "admin_user", "id": str(created["_id"])},
                details={"email": email, "role": "Super Admin"},
            )
            print(f"super admin : {email} created")
            if generated:
                print(f"password    : {password}  (store it now — not saved anywhere)")
    finally:
        close_db_manager()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default="admin@blyns.local")
    parser.add_argument("--name", default="Super Admin")
    parser.add_argument("--password", default=None)
    args = parser.parse_args()
    asyncio.run(main(args.email, args.name, args.password))
