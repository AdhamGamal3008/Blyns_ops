"""In-process ruleset cache (docs/IP_ACCESS_CONTROL_PLAN.md §2-B).

The enforcement middleware (P4) evaluates every request against the compiled
ruleset, so it is cached in-process rather than read from Mongo per request. A
short TTL is the cross-worker propagation backstop: an admin write invalidates
THIS worker's copy immediately (P5), and every other worker refreshes within the
TTL. The loader is injected so the cache is trivially testable.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from app.control_plane.ip_access.matcher import RuleSet, compile_rules

Loader = Callable[[], Awaitable[list[dict]]]


class RuleCache:
    def __init__(self, loader: Loader, ttl_sec: float = 10.0) -> None:
        self._loader = loader
        self._ttl = ttl_sec
        self._ruleset: RuleSet | None = None
        self._expires_at = 0.0

    async def get(self) -> RuleSet:
        now = time.monotonic()
        if self._ruleset is None or now >= self._expires_at:
            self._ruleset = compile_rules(await self._loader())
            self._expires_at = now + self._ttl
        return self._ruleset

    def invalidate(self) -> None:
        """Force the next `get` to reload — call after any rule write."""
        self._ruleset = None
        self._expires_at = 0.0
