"""Admin realm models (docs/AUTH_RBAC.md §2–3).

A role is data, not code: { name, permissions: { resource: Level } }.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.shared.enums import Level

# Admin resources (docs/AUTH_RBAC.md §2). `ip_rules` is the platform-wide IP
# access control panel (docs/IP_ACCESS_CONTROL_PLAN.md §2-F) — distinct from
# `security_policy`, which is a company's per-tenant lockout policy.
ADMIN_RESOURCES = [
    "companies", "seats", "admin_users", "admin_roles",
    "dashboard", "provisioning", "security_policy", "ip_rules",
    "leads",  # discovery-session bookings from the public landing page
]


def _role(name: str, levels: dict[str, Level]) -> dict:
    """Full resource->Level map; anything unspecified defaults to NONE."""
    permissions = {res: int(levels.get(res, Level.NONE)) for res in ADMIN_RESOURCES}
    now = datetime.now(UTC)
    return {
        "name": name,
        "permissions": permissions,
        "is_system": True,
        "created_at": now,
        "updated_at": now,
    }


def default_admin_roles() -> list[dict]:
    """The example admin roles from docs/AUTH_RBAC.md §2, seeded by
    scripts/seed_control_plane.py. Editable data after seeding.

    Operator gets provisioning=READ (unspecified in the spec): they onboard
    companies (companies WRITE) so they can poll job progress.
    """
    w, r, v = Level.WRITE, Level.READ, Level.VIEW
    return [
        _role("Super Admin", {res: w for res in ADMIN_RESOURCES}),
        _role("Operator", {
            "companies": w, "seats": w, "security_policy": w,
            "dashboard": r, "provisioning": r,
            "leads": w,  # operators work the discovery-booking pipeline
            # admin_users / admin_roles: NONE
        }),
        _role("Auditor", {"dashboard": r, "companies": r, "leads": r}),
        _role("Observer", {"dashboard": v, "leads": v}),
    ]
