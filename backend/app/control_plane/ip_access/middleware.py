"""IP access enforcement middleware (docs/IP_ACCESS_CONTROL_PLAN.md §2-C, P4).

Shaped like `RateLimitMiddleware` (docs/ARCHITECTURE.md §6) and mounted *outside*
it (registered last in `main.py`, so outermost / first to run) — a blocked IP is
rejected before it can consume a rate-limit slot. Per request it wires the P1–P3
pieces together:

    ip = client_ip(request)  ->  ruleset = RuleCache.get()
    country = GeoIpResolver.country(ip)  ->  decide(ip, ruleset, country) -> 403 / pass

Design guarantees (D3 = client + admin: this guards the admin portal too, so it
must never lock everyone out):

- **Kill switch** — `cfg.ip_filter_enabled=False` bypasses everything (an operator
  can flip `ERP_IP_FILTER_ENABLED=false` without the UI, even if the UI is blocked).
- **Fail open** — any internal error (ruleset load, geo lookup, decision) ALLOWS
  the request and logs loudly; the filter can never take the platform down.
- **Opaque deny** — a blocked client gets a generic 403 `IP_BLOCKED` / "Access
  denied."; the matched rule is never revealed to the caller.
- **Accounted** — a block is fed to the same `rate_limit_buckets` the dashboard
  reads, so blocks can be charted (never breaks the request if accounting fails).

The Mongo-backed ruleset cache and the geo resolver are built lazily on first use
(the DB manager only exists once the app lifespan has run — same reason the rate
limiter builds its Mongo store lazily) and can be injected for tests.
"""

from __future__ import annotations

import logging

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.control_plane.ip_access.cache import RuleCache
from app.control_plane.ip_access.geoip import GeoIpResolver
from app.control_plane.ip_access.matcher import decide
from app.core.client_ip import client_ip
from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.errors import IP_BLOCKED, error_body
from app.core.rate_limit import record_ip_block

logger = logging.getLogger(__name__)


class IPAccessMiddleware:
    """Platform-wide IP allow/deny + country filter. Returns 403 for a blocked
    client before auth or the rate limiter run."""

    def __init__(
        self,
        app: ASGIApp,
        cfg: Settings | None = None,
        *,
        cache: RuleCache | None = None,
        geo: GeoIpResolver | None = None,
    ) -> None:
        self.app = app
        self.cfg = cfg or default_settings
        self._cache = cache
        self._geo = geo

    def _rule_cache(self) -> RuleCache:
        """The shared ruleset cache the admin API invalidates on writes; an
        injected cache (tests) wins."""
        if self._cache is not None:
            return self._cache
        from app.control_plane.ip_access.runtime import get_rule_cache

        return get_rule_cache(self.cfg)

    def _geoip(self) -> GeoIpResolver:
        """The shared self-hosted geo resolver (no-op when unset); an injected
        resolver (tests) wins."""
        if self._geo is not None:
            return self._geo
        from app.control_plane.ip_access.runtime import get_geo_resolver

        return get_geo_resolver(self.cfg)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Only HTTP is filtered; lifespan/websocket pass straight through.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Kill switch: bypass all filtering (no rule load, no geo, no accounting).
        if not self.cfg.ip_filter_enabled:
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        try:
            ruleset = await self._rule_cache().get()
            ip = client_ip(request, self.cfg.ip_trusted_proxies)
            country = self._geoip().country(ip)
            decision = decide(ip, ruleset, country)
        except Exception:
            # Fail open: a ruleset/geo/decision failure must never take the app
            # down (docs/IP_ACCESS_CONTROL_PLAN.md D5). Allow + log loudly.
            logger.exception("ip_access: filter error; failing open (allowing request)")
            await self.app(scope, receive, send)
            return

        if decision.allowed:
            await self.app(scope, receive, send)
            return

        # Blocked: account for it (fire-safe), then return an opaque 403 that
        # never names the matched rule.
        await record_ip_block(request)
        response: Response = JSONResponse(
            status_code=403,
            content=error_body(IP_BLOCKED, "Access denied."),
        )
        await response(scope, receive, send)
