"""Health endpoint + app-wide envelope against a real (ephemeral) Mongo."""

from __future__ import annotations


async def test_health_ok(client):
    res = await client.get("/health")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["status"] == "ok"
    assert data["mongo"] is True
    assert data["env"] == "test"
    assert "version" in data


async def test_unknown_route_renders_error_envelope(client):
    res = await client.get("/api/v1/does-not-exist")
    assert res.status_code == 404
    body = res.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert set(body["error"].keys()) == {"code", "message", "details"}


async def test_docs_enabled_in_test_env(client):
    assert (await client.get("/docs")).status_code == 200
