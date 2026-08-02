"""IP access enforcement middleware (docs/IP_ACCESS_CONTROL_PLAN.md §2-C, P4).

Drives the ASGI callable directly with a controlled `client` peer + headers and
injected ruleset cache / geo resolver, so every branch is exercised without Mongo
or the geo dataset: deny -> 403 IP_BLOCKED, allowlist wins, kill switch, fail-open,
country geo-deny, trusted-proxy XFF, non-http passthrough, and block accounting.
"""

from __future__ import annotations

import json

from app.control_plane.ip_access.cache import RuleCache
from app.control_plane.ip_access.geoip import GeoIpResolver
from app.control_plane.ip_access.middleware import IPAccessMiddleware
from app.core.config import Settings

_RECORD = "app.control_plane.ip_access.middleware.record_ip_block"


def _cfg(**over) -> Settings:
    over.setdefault("ip_filter_enabled", True)
    return Settings(_env_file=None, jwt_secret="t", **over)


def _rule(kind, match_type, value, enabled=True, rid="r") -> dict:
    return {"_id": rid, "kind": kind, "match_type": match_type,
            "value": value, "enabled": enabled}


def _cache(rules: list[dict]) -> RuleCache:
    async def _load() -> list[dict]:
        return rules

    return RuleCache(_load, ttl_sec=1000)


class _FakeReader:
    def __init__(self, table: dict[str, object]) -> None:
        self._table = table

    def get(self, ip: str) -> object:
        return self._table.get(ip)


class _InnerApp:
    """Terminal ASGI app: 200 OK, remembers whether the request reached it."""

    def __init__(self) -> None:
        self.called = False

    async def __call__(self, scope, receive, send) -> None:
        self.called = True
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": b'{"ok":true}'})


async def _drive(mw, *, client=("203.0.113.9", 1234), headers=None, scope_type="http"):
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {"type": scope_type, "method": "GET", "path": "/x",
             "query_string": b"", "scheme": "http", "headers": raw,
             "client": client, "server": ("test", 80)}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    sent: list[dict] = []

    async def send(msg):
        sent.append(msg)

    await mw(scope, receive, send)
    return sent


def _status(sent) -> int | None:
    return next((m["status"] for m in sent if m["type"] == "http.response.start"), None)


def _body(sent) -> dict | None:
    msg = next((m for m in sent if m["type"] == "http.response.body"), None)
    return json.loads(msg["body"]) if msg else None


def _no_geo() -> GeoIpResolver:
    return GeoIpResolver(None)


async def test_denied_ip_returns_403_ip_blocked_and_is_accounted(monkeypatch):
    calls: list = []

    async def fake_record(request):
        calls.append(request)

    monkeypatch.setattr(_RECORD, fake_record)

    inner = _InnerApp()
    mw = IPAccessMiddleware(
        inner, _cfg(), cache=_cache([_rule("deny", "ip", "203.0.113.9")]), geo=_no_geo()
    )
    sent = await _drive(mw, client=("203.0.113.9", 5))

    assert _status(sent) == 403
    body = _body(sent)
    assert body is not None
    assert body["error"]["code"] == "IP_BLOCKED"
    assert body["error"]["message"] == "Access denied."  # generic — names no rule
    assert inner.called is False   # short-circuited before the app / rate limiter
    assert len(calls) == 1         # the block was accounted


async def test_allowlisted_ip_passes_and_is_not_accounted(monkeypatch):
    calls: list = []

    async def fake_record(request):
        calls.append(request)

    monkeypatch.setattr(_RECORD, fake_record)

    inner = _InnerApp()
    rules = [_rule("deny", "cidr", "203.0.113.0/24", rid="d"),
             _rule("allow", "ip", "203.0.113.9", rid="a")]
    mw = IPAccessMiddleware(inner, _cfg(), cache=_cache(rules), geo=_no_geo())
    sent = await _drive(mw, client=("203.0.113.9", 5))

    assert _status(sent) == 200 and inner.called is True
    assert calls == []  # an allowed request is not counted as a block


async def test_no_rules_defaults_allow():
    inner = _InnerApp()
    mw = IPAccessMiddleware(inner, _cfg(), cache=_cache([]), geo=_no_geo())
    assert _status(await _drive(mw)) == 200 and inner.called is True


async def test_kill_switch_bypasses_without_loading_rules(monkeypatch):
    calls: list = []

    async def fake_record(request):
        calls.append(request)

    monkeypatch.setattr(_RECORD, fake_record)

    loaded = {"n": 0}

    async def _load():
        loaded["n"] += 1
        return [_rule("deny", "cidr", "0.0.0.0/0")]  # would block everything

    inner = _InnerApp()
    mw = IPAccessMiddleware(
        inner, _cfg(ip_filter_enabled=False),
        cache=RuleCache(_load, ttl_sec=1000), geo=_no_geo(),
    )
    sent = await _drive(mw, client=("203.0.113.9", 5))

    assert _status(sent) == 200 and inner.called is True
    assert loaded["n"] == 0  # ruleset never even consulted
    assert calls == []


async def test_disabled_rule_is_inert():
    inner = _InnerApp()
    mw = IPAccessMiddleware(
        inner, _cfg(),
        cache=_cache([_rule("deny", "ip", "203.0.113.9", enabled=False)]),
        geo=_no_geo(),
    )
    assert _status(await _drive(mw, client=("203.0.113.9", 5))) == 200
    assert inner.called is True


async def test_fail_open_when_ruleset_load_errors(monkeypatch):
    calls: list = []

    async def fake_record(request):
        calls.append(request)

    monkeypatch.setattr(_RECORD, fake_record)

    async def _boom():
        raise RuntimeError("control DB unreachable")

    inner = _InnerApp()
    mw = IPAccessMiddleware(
        inner, _cfg(), cache=RuleCache(_boom, ttl_sec=1000), geo=_no_geo()
    )
    sent = await _drive(mw, client=("203.0.113.9", 5))

    assert _status(sent) == 200 and inner.called is True  # failed OPEN
    assert calls == []


async def test_country_deny_uses_geo_resolver():
    reader = _FakeReader({"1.2.3.4": {"country": {"iso_code": "KP"}},
                          "8.8.8.8": {"country": {"iso_code": "US"}}})
    rules = [_rule("deny", "country", "KP")]

    blocked = IPAccessMiddleware(
        _InnerApp(), _cfg(), cache=_cache(rules), geo=GeoIpResolver(reader)
    )
    assert _status(await _drive(blocked, client=("1.2.3.4", 5))) == 403

    inner = _InnerApp()
    allowed = IPAccessMiddleware(
        inner, _cfg(), cache=_cache(rules), geo=GeoIpResolver(reader)
    )
    assert _status(await _drive(allowed, client=("8.8.8.8", 5))) == 200
    assert inner.called is True


async def test_trusted_proxy_xff_determines_client_ip():
    rules = [_rule("deny", "ip", "203.0.113.9")]

    # Socket peer IS a trusted proxy: XFF carries the (denied) real client -> block.
    trusted = IPAccessMiddleware(
        _InnerApp(), _cfg(ip_trusted_proxies=["10.0.0.1"]),
        cache=_cache(rules), geo=_no_geo(),
    )
    sent = await _drive(trusted, client=("10.0.0.1", 9),
                        headers={"X-Forwarded-For": "203.0.113.9"})
    assert _status(sent) == 403

    # Untrusted peer: the same spoofed XFF is ignored, socket IP is used -> allow.
    inner = _InnerApp()
    untrusted = IPAccessMiddleware(
        inner, _cfg(ip_trusted_proxies=[]), cache=_cache(rules), geo=_no_geo()
    )
    sent2 = await _drive(untrusted, client=("198.51.100.7", 9),
                         headers={"X-Forwarded-For": "203.0.113.9"})
    assert _status(sent2) == 200 and inner.called is True


async def test_non_http_scope_passes_through():
    inner = _InnerApp()
    mw = IPAccessMiddleware(
        inner, _cfg(), cache=_cache([_rule("deny", "cidr", "0.0.0.0/0")]), geo=_no_geo()
    )
    # A deny-all ruleset would 403 an HTTP request; a lifespan scope must be
    # delegated untouched instead.
    await _drive(mw, scope_type="lifespan")
    assert inner.called is True
