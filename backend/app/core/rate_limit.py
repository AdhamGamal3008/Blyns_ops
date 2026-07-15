"""Custom rate limiting (docs/ARCHITECTURE.md §6). No external service.

Phase 1 ships the global per-IP fixed-window middleware with an in-process
store (the `local`/`test` backend). The Mongo-backed store (TTL-indexed
`rate_limit_buckets`, survives multiple production workers) and the per-tenant
counters that feed the admin dashboard land with Phase 4 (metrics) and
Phase 11 (hardening) — the store interface below is what they plug into.
"""

from __future__ import annotations

import time

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.errors import RATE_LIMITED, error_body


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


class RateLimitMiddleware:
    """Global per-IP fixed window. 429 + Retry-After when exceeded."""

    def __init__(self, app: ASGIApp, cfg: Settings | None = None) -> None:
        self.app = app
        self.cfg = cfg or default_settings
        self.store = InMemoryFixedWindowStore()

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not self.cfg.rate_limit_enabled:
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        client_ip = request.client.host if request.client else "unknown"
        window_sec = self.cfg.rate_limit_window_sec
        window = int(time.time()) // window_sec

        count = self.store.incr(client_ip, window)
        if count > self.cfg.rate_limit_max_requests:
            retry_after = window_sec - (int(time.time()) % window_sec)
            response: Response = JSONResponse(
                status_code=429,
                content=error_body(RATE_LIMITED, "Too many requests."),
                headers={"Retry-After": str(retry_after)},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
