"""Platform dashboard + metrics + audit log (docs/ADMIN_PORTAL.md §4–5).

GET /admin/dashboard — dashboard READ gets the four full panels; VIEW gets
headline counts only (no drill-down). Everything computed in-app: psutil
(live), platform_metrics snapshots, rate_limit_buckets. No external service.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query

from app.control_plane.metrics.collector import (
    collect_platform_metrics,
    latest_tenant_snapshots,
    storage_trend,
)
from app.control_plane.metrics.host import sample_host
from app.core.audit import write_admin_audit
from app.core.db import get_db_manager
from app.shared.enums import Level
from app.shared.schemas import PaginationParams, envelope, page_meta, to_api
from app.tenant.deps import AdminPrincipal, get_control_db, require_admin

router = APIRouter(prefix="/api/v1/admin", tags=["admin-dashboard"])


async def _rates_panel(control) -> dict:
    """Requests/min + 429s from rate_limit_buckets (§4.2)."""
    since = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=1)
    platform = {"requests": 0, "rate_limited": 0, "ip_blocked": 0}
    async for b in control.rate_limit_buckets.find(
        {"scope": "platform", "minute": {"$gte": since}}
    ):
        platform["requests"] += b.get("requests", 0)
        platform["rate_limited"] += b.get("rate_limited", 0)
        platform["ip_blocked"] += b.get("ip_blocked", 0)

    top_tenants = [doc async for doc in control.rate_limit_buckets.aggregate([
        {"$match": {"scope": "tenant", "minute": {"$gte": since}}},
        {"$group": {"_id": "$key", "requests": {"$sum": "$requests"}}},
        {"$sort": {"requests": -1}},
        {"$limit": 5},
    ])]
    total_tenant_requests = sum(t["requests"] for t in top_tenants) or 1
    return {
        "requests_last_min": platform["requests"],
        "rate_limited_last_min": platform["rate_limited"],
        "ip_blocked_last_min": platform["ip_blocked"],
        "top_tenants": [
            {"tenant": t["_id"], "requests": t["requests"],
             "share_pct": round(100 * t["requests"] / total_tenant_requests, 1)}
            for t in top_tenants
        ],
    }


async def _activity_panel(control, snapshots: list[dict]) -> dict:
    """Cross-tenant business activity (§4.4) from registry + snapshots."""
    now = datetime.now(UTC)
    companies_total = await control.companies.count_documents({})
    companies_active = await control.companies.count_documents({"status": "active"})
    companies_new_7d = await control.companies.count_documents(
        {"created_at": {"$gte": now - timedelta(days=7)}}
    )
    by_tenant = {s["tenant_id"]: s for s in snapshots}
    per_company = []
    async for c in control.companies.find({}):
        snap = by_tenant.get(str(c["_id"]), {}).get("metrics", {})
        per_company.append({
            "company_id": str(c["_id"]),
            "name": c["name"], "slug": c["slug"], "status": c["status"],
            "seats_used": c["seats_used"], "seat_limit": c["seat_limit"],
            "last_activity_at": snap.get("last_activity_at"),
            "logins_24h": snap.get("logins_24h", 0),
            "active_users_24h": snap.get("active_users_24h", 0),
            "module_usage": snap.get("module_usage", {}),
        })
    return {
        "companies_total": companies_total,
        "companies_active": companies_active,
        "companies_new_7d": companies_new_7d,
        "active_users_24h_total": sum(p["active_users_24h"] for p in per_company),
        "per_company": per_company,
    }


@router.get("/dashboard")
async def dashboard(
    admin: AdminPrincipal = Depends(require_admin("dashboard", Level.VIEW)),
):
    control = get_control_db()
    snapshots = await latest_tenant_snapshots(control)
    storage_total = sum(s["metrics"].get("storage_size", 0) for s in snapshots)

    if admin.level_for("dashboard") == Level.VIEW:
        # headline counts only — no drill-down (§4)
        return envelope({
            "companies_total": await control.companies.count_documents({}),
            "companies_active": await control.companies.count_documents(
                {"status": "active"}
            ),
            "storage_total": storage_total,
        })

    host = await asyncio.to_thread(sample_host)  # 1s CPU sample off the loop
    control_snap = await control.platform_metrics.find_one(
        {"scope": "control"}, sort=[("captured_at", -1)]
    )
    return envelope(to_api({
        "host": host,
        "rates": await _rates_panel(control),
        "storage": {
            "control": control_snap["metrics"] if control_snap else None,
            "tenants": [
                {"tenant_id": s["tenant_id"], "slug": s.get("slug"),
                 "captured_at": s["captured_at"],
                 **{k: s["metrics"].get(k) for k in
                    ("data_size", "storage_size", "index_size", "objects")}}
                for s in sorted(
                    snapshots,
                    key=lambda x: x["metrics"].get("storage_size", 0), reverse=True,
                )
            ],
            "total_storage": storage_total,
            "trend": await storage_trend(control),
        },
        "activity": await _activity_panel(control, snapshots),
    }))


@router.post("/metrics/collect")
async def collect_now(
    admin: AdminPrincipal = Depends(require_admin("dashboard", Level.WRITE)),
):
    """Manual snapshot trigger (§5)."""
    summary = await collect_platform_metrics(get_db_manager())
    await write_admin_audit(
        actor_id=str(admin.user["_id"]),
        action="metrics.collected",
        target={"type": "platform_metrics"},
        details={"tenants": summary["tenants"]},
    )
    return envelope(to_api(summary))


@router.get("/audit-log")
async def audit_log(
    params: PaginationParams = Depends(),
    action: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    admin: AdminPrincipal = Depends(require_admin("dashboard", Level.READ)),
):
    control = get_control_db()
    query: dict = {}
    if action:
        query["action"] = action
    if actor:
        query["actor_id"] = actor
    total = await control.admin_audit_log.count_documents(query)
    docs = await (
        control.admin_audit_log.find(query)
        .sort("occurred_at", -1).skip(params.skip).limit(params.page_size)
    ).to_list(length=params.page_size)
    return envelope(
        to_api(docs), meta=page_meta(params.page, params.page_size, total)
    )
