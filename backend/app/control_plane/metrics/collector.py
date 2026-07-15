"""Platform metrics collector (docs/ADMIN_PORTAL.md §4, MULTITENANCY.md §6).

Writes rolling snapshots into control.platform_metrics so the dashboard never
fans out live queries to every tenant DB. Triggered by the in-process
scheduled loop (main.py lifespan) or manually via POST /admin/metrics/collect.
Host stats are NOT snapshotted — the dashboard samples them live (perf note).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.db import DBManager


async def ensure_metrics_indexes(control_db) -> None:
    await control_db.platform_metrics.create_index(
        [("scope", 1), ("tenant_id", 1), ("captured_at", -1)]
    )


async def _db_stats(db) -> dict:
    stats = await db.command("dbStats")
    return {
        "data_size": int(stats.get("dataSize", 0)),
        "storage_size": int(stats.get("storageSize", 0)),
        "index_size": int(stats.get("indexSize", 0)),
        "objects": int(stats.get("objects", 0)),
    }


async def _tenant_activity(tenant_db, now: datetime) -> dict:
    since_24h = now - timedelta(hours=24)
    since_7d = now - timedelta(days=7)
    logins_24h = await tenant_db.activity_log.count_documents(
        {"action": "auth.login", "occurred_at": {"$gte": since_24h}}
    )
    active_users_24h = len(
        await tenant_db.activity_log.distinct(
            "actor_id", {"occurred_at": {"$gte": since_24h}}
        )
    )
    last = await tenant_db.activity_log.find_one({}, sort=[("occurred_at", -1)])
    module_usage = {
        doc["_id"]: doc["count"]
        async for doc in tenant_db.activity_log.aggregate([
            {"$match": {"occurred_at": {"$gte": since_7d}, "module": {"$ne": None}}},
            {"$group": {"_id": "$module", "count": {"$sum": 1}}},
        ])
    }
    return {
        "logins_24h": logins_24h,
        "active_users_24h": active_users_24h,
        "last_activity_at": last["occurred_at"] if last else None,
        "module_usage": module_usage,
    }


async def collect_platform_metrics(dbm: DBManager) -> dict:
    """One snapshot pass: control dbStats + per-tenant dbStats/activity."""
    control = dbm.control
    await ensure_metrics_indexes(control)
    now = datetime.now(UTC)

    await control.platform_metrics.insert_one({
        "captured_at": now,
        "scope": "control",
        "tenant_id": None,
        "metrics": await _db_stats(control),
    })

    tenants = 0
    async for company in control.companies.find(
        {"status": {"$nin": ["provisioning", "failed"]}}
    ):
        tenant_db = dbm.tenant(company["db_name"])
        metrics = await _db_stats(tenant_db)
        metrics.update(await _tenant_activity(tenant_db, now))
        await control.platform_metrics.insert_one({
            "captured_at": now,
            "scope": "tenant",
            "tenant_id": str(company["_id"]),
            "slug": company["slug"],
            "db_name": company["db_name"],
            "metrics": metrics,
        })
        tenants += 1

    return {"captured_at": now, "tenants": tenants}


async def latest_tenant_snapshots(control_db) -> list[dict]:
    """Most recent snapshot per tenant."""
    return [doc async for doc in control_db.platform_metrics.aggregate([
        {"$match": {"scope": "tenant"}},
        {"$sort": {"captured_at": -1}},
        {"$group": {"_id": "$tenant_id", "doc": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$doc"}},
    ])]


async def storage_trend(control_db, limit: int = 24) -> list[dict]:
    """Recent control-scope snapshots → growth trend points."""
    docs = await control_db.platform_metrics.find(
        {"scope": "control"}, sort=[("captured_at", -1)], limit=limit
    ).to_list(length=limit)
    return [
        {"captured_at": d["captured_at"], "data_size": d["metrics"]["data_size"]}
        for d in reversed(docs)
    ]
