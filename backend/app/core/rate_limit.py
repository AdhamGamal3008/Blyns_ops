"""Custom rate limiting + request accounting (docs/ARCHITECTURE.md §6). No
external service.

Two concerns in one middleware:
- ENFORCEMENT: global per-IP fixed window (in-process store for local/test;
  the Mongo-backed store that survives multiple production workers lands with
  Phase 11 hardening — it plugs into the same store interface).
- ACCOUNTING: per-minute request counters, platform-wide and per tenant, into
  the TTL-indexed `rate_limit_buckets` collection. These feed the admin
  dashboard "rate limits / activity" panel (docs/ADMIN_PORTAL.md §4.2).
  Accounting always runs (even when enforcement is disabled) and must never
  break a request — failures are swallowed.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import jwt
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.errors import RATE_LIMITED, error_body

BUCKET_TTL_SEC = 2 * 3600


class InMemoryFixedWindowStore:
    """Fixed-window counters keyed by (key, window). In-process only."""

    def __init__(self) -> None:
        self._counts: dict[tuple[str, int], int] = {}

    def incr(self, key: str, window: int) -> int:
        bucket = (key, window)
        self._counts[bucket] = self._counts.get(bucket, 0) + 1
        # Opportunistic pruning of expired windows so the dict can't grow unbounded.
        if len(self._counts) > 10_000:
            self._counts = {k: v for k, v in self._counts.items() if k[1] >= window}
        return self._counts[bucket]


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


async def _record(request: Request, rate_limited: bool) -> None:
    """Increment platform + tenant minute buckets. Fire-safe."""
    try:
        from app.core.db import get_db_manager

        control = get_db_manager().control
        minute = datetime.now(UTC).replace(second=0, microsecond=0)
        inc = {"requests": 1, "rate_limited": 1 if rate_limited else 0}
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


async def ensure_bucket_indexes(control_db) -> None:
    await control_db.rate_limit_buckets.create_index(
        [("scope", 1), ("key", 1), ("minute", 1)], unique=True
    )
    await control_db.rate_limit_buckets.create_index(
        "minute", expireAfterSeconds=BUCKET_TTL_SEC
    )


class RateLimitMiddleware:
    """Global per-IP fixed window. 429 + Retry-After when exceeded."""

    def __init__(self, app: ASGIApp, cfg: Settings | None = None) -> None:
        self.app = app
        self.cfg = cfg or default_settings
        self.store = InMemoryFixedWindowStore()

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        limited = False
        if self.cfg.rate_limit_enabled:
            client_ip = request.client.host if request.client else "unknown"
            window_sec = self.cfg.rate_limit_window_sec
            window = int(time.time()) // window_sec
            count = self.store.incr(client_ip, window)
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
