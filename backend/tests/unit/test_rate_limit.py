"""Global per-IP fixed-window rate limiter (docs/ARCHITECTURE.md §6)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.rate_limit import RateLimitMiddleware


def _app(**cfg_overrides) -> FastAPI:
    cfg = Settings(_env_file=None, jwt_secret="t", **cfg_overrides)
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, cfg=cfg)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return app


def test_requests_over_limit_get_429_with_retry_after():
    client = TestClient(_app(
        rate_limit_enabled=True, rate_limit_max_requests=3, rate_limit_window_sec=60,
    ))
    for _ in range(3):
        assert client.get("/ping").status_code == 200
    res = client.get("/ping")
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "RATE_LIMITED"
    assert 0 < int(res.headers["Retry-After"]) <= 60


def test_disabled_limiter_passes_everything():
    client = TestClient(_app(rate_limit_enabled=False, rate_limit_max_requests=1))
    for _ in range(10):
        assert client.get("/ping").status_code == 200
