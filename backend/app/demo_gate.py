"""Opt-in HTTP Basic auth gate + SPA mount, used only when sharing a demo publicly.

Enabled solely by env vars (read raw here, NOT via ERP_-prefixed Settings, so the
demo surface never leaks into production config). Absent those vars, calling these
functions is a no-op, so normal local development is untouched
(docs/DEMO_SHARING_PLAN.md).
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Scope

_TRUTHY = {"1", "true", "yes", "on"}
_COOKIE_NAME = "erp_demo_gate"


def _enabled(var: str) -> bool:
    return os.getenv(var, "").strip().lower() in _TRUTHY


class _SPAStaticFiles(StaticFiles):
    """StaticFiles that falls back to index.html for any unmatched path.

    The frontend uses BrowserRouter (real paths, not hash routing), so a client
    deep link or a reload on e.g. /projects/123 arrives at the server as that
    path. Bare StaticFiles(html=True) serves index.html for "/" but 404s such
    deep paths; this serves the SPA shell instead so client-side routing can take
    over. Real asset requests still return the real file (docs/DEMO_SHARING_PLAN.md).
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


def install_demo_gate(app: FastAPI) -> None:
    """Require HTTP Basic credentials on every request, including mounts.

    Implemented as middleware, not a route dependency: Starlette dependencies do
    not run for sub-apps mounted with app.mount(), which would leave the static
    frontend unprotected. MUST be installed LAST (after every other
    add_middleware call) so it is the OUTERMOST wrapper and rejects an
    unauthenticated request before IP filtering, rate limiting, CORS, or access
    logging run — see docs/DEMO_SHARING_PLAN.md §1.

    Cookie handoff: the gate authenticates on the `Authorization` header, but the
    ERP app reuses that same header for its Bearer JWT once a client logs in. So
    after the first successful Basic auth we pin an HttpOnly session cookie and
    admit later requests by that cookie — a cookie is sent on every same-origin
    request regardless of the Authorization header, so the app's Bearer calls are
    not falsely re-challenged (which made the browser re-pop the password prompt).
    """
    if not _enabled("DEMO_GATE_ENABLED"):
        return

    expected_user = os.environ["DEMO_GATE_USER"]
    expected_password = os.environ["DEMO_GATE_PASSWORD"]
    challenge = {"WWW-Authenticate": 'Basic realm="ERP Demo", charset="UTF-8"'}
    # Deterministic (so every uvicorn worker validates it identically) yet
    # unguessable without the password. compare_digest keeps the check constant-time.
    session_token = hashlib.sha256(
        f"demo-gate:v1:{expected_user}:{expected_password}".encode()
    ).hexdigest()

    def _parse(header: str) -> tuple[str, str]:
        if not header.lower().startswith("basic "):
            return "", ""
        try:
            decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
        except (binascii.Error, ValueError, UnicodeDecodeError):
            return "", ""
        user, sep, password = decoded.partition(":")
        return (user, password) if sep else ("", "")

    @app.middleware("http")
    async def _demo_gate(request: Request, call_next):
        import secrets  # local import keeps cost at zero when disabled

        # 1) Browser already unlocked this session: admit by cookie. Survives the
        #    app overwriting Authorization with its Bearer JWT.
        cookie = request.cookies.get(_COOKIE_NAME, "")
        if cookie and secrets.compare_digest(cookie, session_token):
            return await call_next(request)

        # 2) Valid Basic credentials (the initial browser prompt): admit and pin
        #    the session cookie so subsequent Bearer-carrying calls aren't re-challenged.
        user, password = _parse(request.headers.get("authorization", ""))
        user_ok = secrets.compare_digest(user, expected_user)
        password_ok = secrets.compare_digest(password, expected_password)
        if user_ok and password_ok:
            response = await call_next(request)
            response.set_cookie(
                _COOKIE_NAME, session_token,
                httponly=True, samesite="lax", path="/",
            )
            return response

        # 3) Neither → challenge.
        return Response(status_code=401, headers=challenge)


def mount_built_frontend(app: FastAPI, dist_dir: Path) -> None:
    """Serve the production React build from the same origin as the API.

    Must be called AFTER every API router is registered — a mount at "/" is greedy
    and shadows routes added after it. html=True serves index.html for "/" and
    falls back to index.html for unknown paths, which is what the client-side
    react-router needs (docs/DEMO_SHARING_PLAN.md §A).
    """
    if not _enabled("SERVE_FRONTEND"):
        return
    if not dist_dir.is_dir():
        raise RuntimeError(
            f"SERVE_FRONTEND is on but the build directory does not exist: {dist_dir}"
        )
    app.mount("/", _SPAStaticFiles(directory=str(dist_dir), html=True), name="spa")
