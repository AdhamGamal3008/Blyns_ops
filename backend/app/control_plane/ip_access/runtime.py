"""Process-wide IP-access singletons (docs/IP_ACCESS_CONTROL_PLAN.md §2-B, P5).

The enforcement middleware (P4) evaluates every request against a cached ruleset;
the admin API (P5) mutates the rules. They must share ONE `RuleCache` instance so a
write can `invalidate()` exactly what the middleware reads — otherwise a new rule
would not take effect on this worker until the TTL lapsed. The geo resolver is
shared for the same reason (open the `.mmdb` once, reuse everywhere).

Both are process-local and built lazily (the DB manager and the dataset only exist
once the app lifespan has run). In a multi-worker deployment each worker holds its
own pair: an admin write invalidates the worker that served it immediately, and the
others refresh within the cache TTL (`ip_rule_cache_ttl_sec`) — the documented
cross-worker propagation backstop.
"""

from __future__ import annotations

from app.control_plane.ip_access.cache import RuleCache
from app.control_plane.ip_access.geoip import GeoIpResolver, build_geoip_resolver
from app.control_plane.ip_access.repository import enabled_rules
from app.core.config import Settings
from app.core.config import settings as default_settings

_rule_cache: RuleCache | None = None
_geo_resolver: GeoIpResolver | None = None


async def _load_enabled_rules() -> list[dict]:
    from app.core.db import get_db_manager

    return await enabled_rules(get_db_manager().control)


def get_rule_cache(cfg: Settings | None = None) -> RuleCache:
    """The shared compiled-ruleset cache (built on first use)."""
    global _rule_cache
    if _rule_cache is None:
        cfg = cfg or default_settings
        _rule_cache = RuleCache(_load_enabled_rules, ttl_sec=cfg.ip_rule_cache_ttl_sec)
    return _rule_cache


def get_geo_resolver(cfg: Settings | None = None) -> GeoIpResolver:
    """The shared IP→country resolver (a fail-open no-op until a dataset is set)."""
    global _geo_resolver
    if _geo_resolver is None:
        cfg = cfg or default_settings
        _geo_resolver = build_geoip_resolver(cfg.ip_geoip_db_path)
    return _geo_resolver


def invalidate_rule_cache() -> None:
    """Force this worker's next lookup to reload — call after ANY rule write."""
    if _rule_cache is not None:
        _rule_cache.invalidate()


def reset_runtime() -> None:
    """Test hook: forget both singletons so the next call rebuilds them against the
    current config / DB. Not used in production."""
    global _rule_cache, _geo_resolver
    _rule_cache = None
    _geo_resolver = None
