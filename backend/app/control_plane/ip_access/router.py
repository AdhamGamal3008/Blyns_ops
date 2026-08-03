"""Admin IP access rules API (docs/IP_ACCESS_CONTROL_PLAN.md §2-F, P5).

Control realm, gated on the `ip_rules` admin resource, every write audited. Two
allow/deny lists plus the IP tester back the admin portal panel (P7). Enforcement
lives in the middleware (P4); this is the management surface.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.control_plane.ip_access import service
from app.control_plane.ip_access.models import (
    IpRuleCreate,
    IpRulePatch,
    IpTestRequest,
)
from app.control_plane.ip_access.runtime import get_geo_resolver
from app.core.client_ip import client_ip
from app.core.config import settings
from app.core.db import get_db_manager
from app.shared.enums import Level
from app.shared.schemas import PaginationParams, envelope, page_meta, to_api
from app.tenant.deps import AdminPrincipal, require_admin

router = APIRouter(prefix="/api/v1/admin/ip-rules", tags=["admin-ip-rules"])


@router.get("")
async def list_rules(
    params: PaginationParams = Depends(),
    kind: str | None = Query(default=None, pattern="^(allow|deny)$"),
    match_type: str | None = Query(default=None, pattern="^(ip|cidr|country)$"),
    enabled: bool | None = Query(default=None),
    admin: AdminPrincipal = Depends(require_admin("ip_rules", Level.READ)),
):
    rows, total = await service.list_rules(
        get_db_manager().control, kind, match_type, enabled,
        skip=params.skip, limit=params.page_size,
    )
    return envelope(
        [to_api(r) for r in rows],
        meta=page_meta(params.page, params.page_size, total),
    )


@router.post("", status_code=201)
async def create_rule(
    payload: IpRuleCreate,
    admin: AdminPrincipal = Depends(require_admin("ip_rules", Level.WRITE)),
):
    rule = await service.create_rule(
        get_db_manager().control, payload, actor_id=str(admin.user["_id"])
    )
    return envelope(to_api(rule))


@router.post("/test")
async def test_ip(
    body: IpTestRequest,
    admin: AdminPrincipal = Depends(require_admin("ip_rules", Level.READ)),
):
    """"Would this IP be allowed, and by which rule?" — check BEFORE adding a rule
    that might block you (docs/IP_ACCESS_CONTROL_PLAN.md §2-H)."""
    return envelope(await service.test_ip(get_db_manager().control, body.ip))


@router.get("/whoami")
async def whoami(
    request: Request,
    admin: AdminPrincipal = Depends(require_admin("ip_rules", Level.READ)),
):
    """The IP (and country) the server sees for THIS admin — powers the add form's
    "this would block your current IP" warning (docs/IP_ACCESS_CONTROL_PLAN.md §2-F)."""
    ip = client_ip(request, settings.ip_trusted_proxies)
    return envelope({"ip": ip, "country": get_geo_resolver(settings).country(ip)})


@router.patch("/{rule_id}")
async def patch_rule(
    rule_id: str,
    patch: IpRulePatch,
    admin: AdminPrincipal = Depends(require_admin("ip_rules", Level.WRITE)),
):
    rule = await service.patch_rule(
        get_db_manager().control, rule_id, patch, actor_id=str(admin.user["_id"])
    )
    return envelope(to_api(rule))


@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: str,
    admin: AdminPrincipal = Depends(require_admin("ip_rules", Level.WRITE)),
):
    await service.delete_rule(
        get_db_manager().control, rule_id, actor_id=str(admin.user["_id"])
    )
    return envelope({"deleted": True})
