"""Error envelope rendering (docs/ARCHITECTURE.md §4)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import DomainError, register_exception_handlers


def _mini_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom():
        raise DomainError(
            "SEAT_LIMIT_REACHED", "Seat limit reached.", http_status=409,
            details={"seat_limit": 5},
        )

    @app.get("/locked")
    async def locked():
        raise DomainError(
            "ACCOUNT_LOCKED", "Account locked.", http_status=423,
            headers={"Retry-After": "900"},
        )

    @app.get("/typed")
    async def typed(count: int):
        return {"count": count}

    return app


def test_domain_error_renders_exact_envelope():
    client = TestClient(_mini_app())
    res = client.get("/boom")
    assert res.status_code == 409
    assert res.json() == {
        "error": {
            "code": "SEAT_LIMIT_REACHED",
            "message": "Seat limit reached.",
            "details": {"seat_limit": 5},
        }
    }


def test_domain_error_headers_pass_through():
    res = TestClient(_mini_app()).get("/locked")
    assert res.status_code == 423
    assert res.headers["Retry-After"] == "900"


def test_validation_error_uses_envelope():
    res = TestClient(_mini_app()).get("/typed", params={"count": "not-a-number"})
    assert res.status_code == 422
    body = res.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"]["errors"]


def test_unknown_route_uses_envelope():
    res = TestClient(_mini_app()).get("/does-not-exist")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"
