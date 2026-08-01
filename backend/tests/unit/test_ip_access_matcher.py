"""IP access matching engine (docs/IP_ACCESS_CONTROL_PLAN.md §2-B, D2 precedence):
allowlist wins → deny ip/cidr → deny country → default allow."""

from __future__ import annotations

from app.control_plane.ip_access.cache import RuleCache
from app.control_plane.ip_access.matcher import compile_rules, decide


def _rule(kind, match_type, value, rid="r", enabled=True):
    return {"_id": rid, "kind": kind, "match_type": match_type,
            "value": value, "enabled": enabled}


def test_default_allow_when_no_rules():
    d = decide("203.0.113.9", compile_rules([]))
    assert d.allowed is True and d.reason == "default_allow"


def test_deny_ip():
    rs = compile_rules([_rule("deny", "ip", "203.0.113.9")])
    assert decide("203.0.113.9", rs).allowed is False
    assert decide("203.0.113.10", rs).allowed is True


def test_deny_cidr_range():
    rs = compile_rules([_rule("deny", "cidr", "203.0.113.0/24")])
    assert decide("203.0.113.55", rs).allowed is False
    assert decide("203.0.114.1", rs).allowed is True


def test_deny_country_needs_resolved_country():
    rs = compile_rules([_rule("deny", "country", "KP")])
    assert decide("1.2.3.4", rs, country="KP").allowed is False
    assert decide("1.2.3.4", rs, country="kp").allowed is False  # case-insensitive
    assert decide("1.2.3.4", rs, country="US").allowed is True
    assert decide("1.2.3.4", rs, country=None).allowed is True   # no geo → cannot deny


def test_allowlist_beats_deny_cidr():
    rs = compile_rules([
        _rule("deny", "cidr", "203.0.113.0/24", rid="d"),
        _rule("allow", "ip", "203.0.113.9", rid="a"),
    ])
    d = decide("203.0.113.9", rs)
    assert d.allowed is True and d.reason == "allowlisted" and d.rule_id == "a"
    assert decide("203.0.113.10", rs).allowed is False  # rest of the range still denied


def test_allow_country_beats_deny_everything():
    rs = compile_rules([
        _rule("deny", "cidr", "0.0.0.0/0", rid="d"),   # deny all IPv4
        _rule("allow", "country", "US", rid="a"),
    ])
    assert decide("8.8.8.8", rs, country="US").allowed is True
    assert decide("8.8.8.8", rs, country="KP").allowed is False


def test_disabled_and_deleted_rules_are_inert():
    rs = compile_rules([_rule("deny", "ip", "203.0.113.9", enabled=False)])
    assert decide("203.0.113.9", rs).allowed is True
    deleted = _rule("deny", "ip", "203.0.113.9")
    deleted["is_deleted"] = True
    assert decide("203.0.113.9", compile_rules([deleted])).allowed is True


def test_ipv6_deny_cidr_does_not_touch_ipv4():
    rs = compile_rules([_rule("deny", "cidr", "2001:db8::/32")])
    assert decide("2001:db8::dead", rs).allowed is False
    assert decide("2001:db9::1", rs).allowed is True
    assert decide("203.0.113.9", rs).allowed is True  # v4 unaffected by a v6 rule


def test_unparseable_ip_defaults_allow_with_reason():
    rs = compile_rules([_rule("deny", "cidr", "203.0.113.0/24")])
    d = decide("unknown", rs)
    assert d.allowed is True and d.reason == "unresolved"


def test_bad_rule_value_is_skipped():
    rs = compile_rules([_rule("deny", "cidr", "not-a-cidr")])
    assert decide("203.0.113.9", rs).allowed is True


def test_matched_rule_details_surface_for_the_test_endpoint():
    rs = compile_rules([_rule("deny", "cidr", "203.0.113.0/24", rid="abc")])
    d = decide("203.0.113.9", rs)
    assert (d.rule_id, d.kind, d.match_type, d.value) == ("abc", "deny", "cidr", "203.0.113.0/24")


# --- ruleset cache -----------------------------------------------------------

async def test_cache_loads_once_within_ttl_then_reloads_on_invalidate():
    calls = {"n": 0}
    rules = [_rule("deny", "ip", "1.2.3.4")]

    async def loader():
        calls["n"] += 1
        return rules

    cache = RuleCache(loader, ttl_sec=1000)
    rs = await cache.get()
    await cache.get()
    assert calls["n"] == 1  # served from cache within the TTL
    assert decide("1.2.3.4", rs).allowed is False

    cache.invalidate()
    await cache.get()
    assert calls["n"] == 2  # reloaded after invalidation


async def test_zero_ttl_reloads_every_get():
    calls = {"n": 0}

    async def loader():
        calls["n"] += 1
        return []

    cache = RuleCache(loader, ttl_sec=0)
    await cache.get()
    await cache.get()
    assert calls["n"] == 2
