"""IP access enforcement through the full app (docs/IP_ACCESS_CONTROL_PLAN.md P4).

A real deny rule in the control DB blocks a matching client at the edge with a
generic 403 IP_BLOCKED, a non-matching client passes (default-allow), and the
block is accounted into the buckets the dashboard reads. `/health` is the probe:
it needs no auth, so this isolates the middleware from the realms it fronts.
"""

from __future__ import annotations

import httpx
import pytest
from asgi_lifespan import LifespanManager

from app.control_plane.ip_access.repository import COLLECTION, insert
from app.control_plane.ip_access.runtime import reset_runtime
from app.core.db import get_db_manager
from app.main import create_app


@pytest.fixture
async def filtered_app(test_settings):
    """Full app with IP filtering ENABLED (the suite default is off). Resets the
    shared ruleset cache so this test's rules are loaded fresh, not served stale
    from a singleton another test warmed."""
    reset_runtime()
    cfg = test_settings.model_copy(update={"ip_filter_enabled": True})
    application = create_app(cfg)
    async with LifespanManager(application):
        yield application
    reset_runtime()


def _client_from(app, ip: str) -> httpx.AsyncClient:
    # ASGITransport's `client` sets scope["client"] — i.e. the socket peer IP.
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=(ip, 40000)),
        base_url="http://test",
    )


async def test_deny_rule_blocks_client_at_the_edge(filtered_app):
    control = get_db_manager().control
    await control[COLLECTION].delete_many({"value": "203.0.113.99"})
    await insert(control, {
        "kind": "deny", "match_type": "ip", "value": "203.0.113.99",
        "enabled": True, "source": "manual",
    })

    async with _client_from(filtered_app, "203.0.113.99") as c:
        blocked = await c.get("/health")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "IP_BLOCKED"

    async with _client_from(filtered_app, "198.51.100.7") as c:
        allowed = await c.get("/health")
    assert allowed.status_code == 200

    # The block was accounted (same buckets the rate limiter / dashboard use).
    bucket = await control.rate_limit_buckets.find_one(
        {"scope": "platform", "ip_blocked": {"$gte": 1}}
    )
    assert bucket is not None


async def test_kill_switch_lets_everyone_through(test_settings):
    """With the filter disabled, even a matching deny rule is bypassed."""
    cfg = test_settings.model_copy(update={"ip_filter_enabled": False})
    app = create_app(cfg)
    async with LifespanManager(app):
        control = get_db_manager().control
        await control[COLLECTION].delete_many({"value": "203.0.113.99"})
        await insert(control, {
            "kind": "deny", "match_type": "ip", "value": "203.0.113.99",
            "enabled": True, "source": "manual",
        })
        async with _client_from(app, "203.0.113.99") as c:
            res = await c.get("/health")
    assert res.status_code == 200
