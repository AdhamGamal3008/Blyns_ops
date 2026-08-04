"""Opt-in demo gate through the full app (docs/DEMO_SHARING_PLAN.md).

Two things must hold: with no demo env vars the gate is INVISIBLE (normal dev is
untouched), and with them set it fronts EVERYTHING — API routes, /docs, and
/openapi.json — because it is middleware, not a route dependency. The gate is
installed outermost, so an unauthenticated request is rejected before the app
does any real work.
"""

from __future__ import annotations

import base64

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

from app.demo_gate import mount_built_frontend
from app.main import create_app

DEMO_USER = "client"
DEMO_PASSWORD = "s3cret-demo-pw"


def _auth(user: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


@pytest.fixture
async def gated_app(test_settings, monkeypatch):
    """Full app with the demo gate ENABLED (the suite default is off)."""
    monkeypatch.setenv("DEMO_GATE_ENABLED", "1")
    monkeypatch.setenv("DEMO_GATE_USER", DEMO_USER)
    monkeypatch.setenv("DEMO_GATE_PASSWORD", DEMO_PASSWORD)
    application = create_app(test_settings)
    async with LifespanManager(application):
        yield application


async def test_gate_off_is_invisible(test_settings, monkeypatch):
    """No demo env vars → install_demo_gate is a no-op → no auth required."""
    monkeypatch.delenv("DEMO_GATE_ENABLED", raising=False)
    monkeypatch.delenv("DEMO_GATE_USER", raising=False)
    monkeypatch.delenv("DEMO_GATE_PASSWORD", raising=False)
    app = create_app(test_settings)
    async with LifespanManager(app):
        async with _client(app) as c:
            health = await c.get("/health")
            docs = await c.get("/docs")
    assert health.status_code == 200
    assert docs.status_code == 200  # /docs is on in test env, and ungated


async def test_missing_credentials_are_challenged(gated_app):
    """Unauthenticated requests get 401 + a Basic challenge, on every surface."""
    async with _client(gated_app) as c:
        for path in ("/health", "/docs", "/openapi.json", "/api/v1/auth/login"):
            r = await c.get(path)
            assert r.status_code == 401, path
            assert r.headers.get("www-authenticate", "").lower().startswith("basic"), path


async def test_wrong_credentials_are_rejected(gated_app):
    async with _client(gated_app) as c:
        bad_pw = await c.get("/openapi.json", headers=_auth(DEMO_USER, "nope"))
        bad_user = await c.get("/openapi.json", headers=_auth("intruder", DEMO_PASSWORD))
        garbage = await c.get("/openapi.json", headers={"Authorization": "Basic !!not-b64!!"})
    assert bad_pw.status_code == 401
    assert bad_user.status_code == 401
    assert garbage.status_code == 401


async def test_correct_credentials_pass_through(gated_app):
    """Valid creds reach the real handlers — API docs AND a live route."""
    async with _client(gated_app) as c:
        openapi = await c.get("/openapi.json", headers=_auth(DEMO_USER, DEMO_PASSWORD))
        health = await c.get("/health", headers=_auth(DEMO_USER, DEMO_PASSWORD))
    assert openapi.status_code == 200
    assert openapi.json()["info"]["title"] == "ERP"
    assert health.status_code == 200


async def test_bearer_after_basic_is_not_rechallenged(gated_app):
    """The reported bug: once a client logs in, the SPA sends Authorization:
    Bearer <jwt>, overwriting the Basic header. Without the cookie handoff the
    gate 401s that (re-popping the browser prompt). With it, the pinned cookie
    admits the request regardless of the Bearer header."""
    async with _client(gated_app) as c:
        # First Basic auth pins the gate cookie (httpx keeps it on the client).
        first = await c.get("/openapi.json", headers=_auth(DEMO_USER, DEMO_PASSWORD))
        assert first.status_code == 200
        assert "erp_demo_gate" in c.cookies

        # App now sends its OWN Bearer token; the Basic header is gone. Must still pass.
        second = await c.get(
            "/openapi.json", headers={"Authorization": "Bearer fake.jwt.token"}
        )
        assert second.status_code == 200
        assert "www-authenticate" not in second.headers  # no re-challenge


async def test_bearer_without_gate_cookie_is_challenged(gated_app):
    """A Bearer header alone (no cookie, no Basic) is still gated — the fix does
    not weaken the gate for fresh clients."""
    async with _client(gated_app) as c:
        r = await c.get(
            "/openapi.json", headers={"Authorization": "Bearer fake.jwt.token"}
        )
    assert r.status_code == 401
    assert r.headers.get("www-authenticate", "").lower().startswith("basic")


# --- SPA mount (docs/DEMO_SHARING_PLAN.md §A) ------------------------------
# Hermetic: builds a throwaway "dist" so these need neither npm nor mongo.


def _fake_dist(tmp_path):
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><div id="root"></div></body></html>',
        encoding="utf-8",
    )
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("// built bundle", encoding="utf-8")
    return tmp_path


async def test_spa_mount_serves_assets_and_falls_back_to_index(tmp_path, monkeypatch):
    """Real assets serve as files; unknown deep paths fall back to index.html
    (BrowserRouter); an API route registered before the mount still wins."""
    monkeypatch.setenv("SERVE_FRONTEND", "1")
    app = FastAPI()

    @app.get("/api/v1/ping")
    async def ping():
        return {"ok": True}

    mount_built_frontend(app, _fake_dist(tmp_path))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        root = await c.get("/")
        deep = await c.get("/projects/123/deep/route")
        asset = await c.get("/assets/app.js")
        api = await c.get("/api/v1/ping")

    assert root.status_code == 200 and "<!doctype html>" in root.text
    assert deep.status_code == 200 and 'id="root"' in deep.text  # SPA fallback
    assert asset.status_code == 200 and "built bundle" in asset.text  # real file
    assert api.status_code == 200 and api.json()["ok"] is True  # API wins over mount


async def test_spa_mount_is_noop_when_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("SERVE_FRONTEND", raising=False)
    app = FastAPI()
    mount_built_frontend(app, tmp_path)  # dir has no index.html — must not raise
    assert not any(getattr(r, "name", None) == "spa" for r in app.routes)


def test_spa_mount_raises_when_enabled_but_build_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("SERVE_FRONTEND", "1")
    with pytest.raises(RuntimeError, match="build directory does not exist"):
        mount_built_frontend(FastAPI(), tmp_path / "nope")
