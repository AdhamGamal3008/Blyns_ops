"""Custom rate limiting + request accounting (docs/ARCHITECTURE.md §6). No
external service.

Two concerns in one middleware:
- ENFORCEMENT: global per-IP fixed window. The store is chosen by environment
  (ENVIRONMENTS.md §1): an in-process dict for local/test, and a Mongo-backed
  store for production so a single limit holds across multiple uvicorn workers
  (one in-process counter per worker would let N workers serve N× the limit).
  Both stores share the async `incr(key, window) -> int` interface.
- ACCOUNTING: per-minute request counters, platform-wide and per tenant, into
  the TTL-indexed `rate_limit_buckets` collection. These feed the admin
  dashboard "rate limits / activity" panel (docs/ADMIN_PORTAL.md §4.2).
  Accounting always runs (even when enforcement is disabled) and must never
  break a request — failures are swallowed.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Protocol

import jwt
from pymongo import ReturnDocument
from pymongo.errors import OperationFailure
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.core.client_ip import client_ip
from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.errors import RATE_LIMITED, error_body

BUCKET_TTL_SEC = 2 * 3600
_ENFORCEMENT_COLL = "rate_limit_windows"


class FixedWindowStore(Protocol):
    """A per-(key, window) counter. `incr` returns the new count for the window."""

    async def incr(self, key: str, window: int) -> int: ...


class InMemoryFixedWindowStore:
    """Fixed-window counters keyed by (key, window). In-process only — correct
    for a single worker (local/test), not across production workers."""

    def __init__(self) -> None:
        self._counts: dict[tuple[str, int], int] = {}

    async def incr(self, key: str, window: int) -> int:
        bucket = (key, window)
        self._counts[bucket] = self._counts.get(bucket, 0) + 1
        # Opportunistic pruning of expired windows so the dict can't grow unbounded.
        if len(self._counts) > 10_000:
            self._counts = {k: v for k, v in self._counts.items() if k[1] >= window}
        return self._counts[bucket]


class MongoFixedWindowStore:
    """Fixed-window counters in a TTL-indexed control-plane collection, shared by
    every worker. The count is an atomic `$inc` inside `find_one_and_update`, so
    concurrent requests across workers can never miss each other's increments.
    """

    def __init__(self, control_db) -> None:
        self._db = control_db

    async def incr(self, key: str, window: int) -> int:
        doc = await self._db[_ENFORCEMENT_COLL].find_one_and_update(
            {"key": key, "window": window},
            {"$inc": {"count": 1}, "$setOnInsert": {"created_at": datetime.now(UTC)}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return int(doc["count"])


_DUPLICATE_KEY = 11000  # MongoDB E11000


async def _merge_duplicate_docs(coll, key_fields, sum_fields) -> None:
    """Collapse rows that violate a soon-to-be-created unique index.

    Upserts that race BEFORE the unique index exists can each insert a row for
    the same key tuple (the classic Mongo upsert race). Once duplicates exist
    the unique index can never build. Merge every duplicate group into a single
    document — summing the counters so no accounting is lost — leaving exactly
    one doc per key tuple. Idempotent: safe to run concurrently from every
    worker (a group already collapsed by another worker simply won't match).
    """
    group: dict = {
        "_id": {f: f"${f}" for f in key_fields},
        "ids": {"$push": "$_id"},
        "n": {"$sum": 1},
    }
    for f in sum_fields:
        group[f] = {"$sum": f"${f}"}
    pipeline = [{"$group": group}, {"$match": {"n": {"$gt": 1}}}]
    async for grp in coll.aggregate(pipeline):
        ids = grp["ids"]
        await coll.update_one(
            {"_id": ids[0]}, {"$set": {f: grp[f] for f in sum_fields}}
        )
        await coll.delete_many({"_id": {"$in": ids[1:]}})


async def _create_unique_index(coll, keys, *, key_fields, sum_fields) -> None:
    """Create a unique index, self-healing a collection already poisoned by
    pre-index duplicate rows: merge the duplicates, then build the index."""
    try:
        await coll.create_index(keys, unique=True)
    except OperationFailure as exc:
        if exc.code != _DUPLICATE_KEY:
            raise
        await _merge_duplicate_docs(coll, key_fields, sum_fields)
        await coll.create_index(keys, unique=True)


async def ensure_enforcement_indexes(control_db) -> None:
    coll = control_db[_ENFORCEMENT_COLL]
    await _create_unique_index(
        coll, [("key", 1), ("window", 1)],
        key_fields=("key", "window"), sum_fields=("count",),
    )
    # windows are created once then only $inc'd, so TTL from creation is safe
    await coll.create_index("created_at", expireAfterSeconds=BUCKET_TTL_SEC)


def _tenant_from_auth_header(request: Request) -> str | None:
    """Metrics-only tenant attribution from the bearer token's claim.
    UNVERIFIED decode — never used for authorization, only accounting."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    try:
        claims = jwt.decode(
            auth[7:], options={"verify_signature": False, "verify_exp": False}
        )
        return claims.get("tenant")
    except jwt.InvalidTokenError:
        return None


async def _bump_buckets(request: Request, inc: dict[str, int]) -> None:
    """Increment the platform + (token-attributed) tenant minute buckets by `inc`.
    Fire-safe: accounting must never break a request."""
    try:
        from app.core.db import get_db_manager

        control = get_db_manager().control
        minute = datetime.now(UTC).replace(second=0, microsecond=0)
        await control.rate_limit_buckets.update_one(
            {"scope": "platform", "key": "platform", "minute": minute},
            {"$inc": inc}, upsert=True,
        )
        tenant = _tenant_from_auth_header(request)
        if tenant:
            await control.rate_limit_buckets.update_one(
                {"scope": "tenant", "key": tenant, "minute": minute},
                {"$inc": inc}, upsert=True,
            )
    except Exception:
        pass  # accounting must never break a request


async def _record(request: Request, rate_limited: bool) -> None:
    """Rate-limiter accounting: every request that reaches the limiter, plus 429s."""
    await _bump_buckets(request, {"requests": 1, "rate_limited": 1 if rate_limited else 0})


async def record_ip_block(request: Request) -> None:
    """IP-filter accounting (docs/IP_ACCESS_CONTROL_PLAN.md §2-C). A blocked request
    is short-circuited before the rate limiter, so count it here — as a request AND
    a block — into the same buckets the admin dashboard reads."""
    await _bump_buckets(request, {"requests": 1, "ip_blocked": 1})


async def ensure_bucket_indexes(control_db) -> None:
    coll = control_db.rate_limit_buckets
    await _create_unique_index(
        coll, [("scope", 1), ("key", 1), ("minute", 1)],
        key_fields=("scope", "key", "minute"),
        sum_fields=("requests", "rate_limited", "ip_blocked"),
    )
    await coll.create_index("minute", expireAfterSeconds=BUCKET_TTL_SEC)


class RateLimitMiddleware:
    """Global per-IP fixed window. 429 + Retry-After when exceeded.

    Store is chosen by environment: in-process for local/test, Mongo-backed for
    production (shared across workers). The Mongo store is built lazily on first
    use because the DB manager is only initialized once the app lifespan runs.
    """

    def __init__(self, app: ASGIApp, cfg: Settings | None = None) -> None:
        self.app = app
        self.cfg = cfg or default_settings
        self._memory_store = InMemoryFixedWindowStore()
        self._mongo_store: MongoFixedWindowStore | None = None

    def _store(self) -> FixedWindowStore:
        if self.cfg.env != "production":
            return self._memory_store
        if self._mongo_store is None:
            from app.core.db import get_db_manager

            self._mongo_store = MongoFixedWindowStore(get_db_manager().control)
        return self._mongo_store

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        limited = False
        if self.cfg.rate_limit_enabled:
            ip = client_ip(request, self.cfg.ip_trusted_proxies)
            window_sec = self.cfg.rate_limit_window_sec
            window = int(time.time()) // window_sec
            count = await self._store().incr(ip, window)
            limited = count > self.cfg.rate_limit_max_requests

        await _record(request, limited)

        if limited:
            retry_after = self.cfg.rate_limit_window_sec - (
                int(time.time()) % self.cfg.rate_limit_window_sec
            )
            response: Response = JSONResponse(
                status_code=429,
                content=error_body(RATE_LIMITED, "Too many requests."),
                headers={"Retry-After": str(retry_after)},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
