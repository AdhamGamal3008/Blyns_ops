# Plan — On-Demand Client Demo Sharing (Cloudflare Quick Tunnel + Basic Auth)

> **This is an implementation plan, not a spec, and nothing here is built yet.**
> A future session must be able to execute it cold, in one sitting. It adds an
> **opt-in, on-demand** way to expose the locally running ERP to a client over a
> public HTTPS URL, gated by HTTP Basic auth, via an anonymous **Cloudflare Quick
> Tunnel** (no Cloudflare account, no domain, no DNS).
>
> The whole feature is **one command** the developer runs only when a demo is
> needed: `python scripts/share_demo.py` → prints URL + credentials, tears down
> cleanly on `Ctrl+C`.
>
> - **Non-negotiables (`CLAUDE.md`):** fully custom, no third-party SaaS / paid
>   APIs / managed services (open-source tools + an anonymous tunnel binary are
>   fine); **no new Python runtime deps** (stdlib + what FastAPI/Starlette already
>   ship); three config-driven environments (`local`/`test`/`production`); **zero
>   impact on normal dev** — every new behavior is gated behind env vars that
>   default OFF; secrets never committed.
> - Paths / line numbers are current as of **2026-08-03**. If a reference has
>   moved, follow the real code.
> - Source: adapted from the `demo-share-cloudflare-quick-tunnel` build spec. The
>   **"Deviations from the source spec"** section at the bottom lists every place
>   this plan intentionally diverges from that spec and why — read it.

---

## 0. What we are building, in one paragraph

A tiny, **opt-in HTTP Basic auth gate** (`backend/app/demo_gate.py`) installed as
ASGI **middleware** (not a route dependency — dependencies do not run for mounted
sub-apps, which would leave the static frontend unprotected) that, **only when an
env var is set**, requires credentials on **every** request: API routes, `/docs`,
`/openapi.json`, and the mounted production React build. A companion helper mounts
the built SPA (`frontend/dist`) at `/` from the **same origin** as the API so
there is no CORS and no absolute-URL breakage behind the tunnel. A single
stdlib-only script (`scripts/share_demo.py`) builds the frontend, boots a gated
`uvicorn`, opens an anonymous `cloudflared` Quick Tunnel, prints a shareable
block, and cleans up every child process on `Ctrl+C`. With the script not
running and the env vars unset, `uvicorn` / `npm run dev` behave **byte-for-byte**
as today.

---

## 1. Baseline — what exists to build on (read first)

| Thing | Where | Note for this feature |
|---|---|---|
| App factory | `backend/app/main.py` → `create_app(cfg)`; module-level `app = create_app()` (main.py:158) | **Not** a flat module-level `app = FastAPI(...)`. Both wiring calls go **inside** `create_app`. |
| `FastAPI(...)` construction | `backend/app/main.py:83-90` (`docs_url` on iff `cfg.docs_enabled`) | Gate must cover `/docs`, `/openapi.json` too — middleware does, by design. |
| Middleware stack | `main.py:99-106` — `AccessLog`, `CORS`, `RateLimit`, `IPAccess`, added in that order | **Order matters — see the load-bearing fact below.** |
| Existing health route | `main.py:108` `@app.get("/health")` — pings Mongo, `envelope(...)`, 200/503 | **Reuse it.** It lives at **`/health`** (root), NOT `/api/v1/health`. No new route needed. |
| Router mounting | `main.py:142-153` — 12 `include_router(...)` calls, all under `/api/v1*` | The SPA mount at `/` must be registered **after** all of these (greedy mount). |
| API prefix | every router: `prefix="/api/v1..."` (e.g. `crm/router.py:32`) | `API_PREFIX = /api/v1`. |
| Config | `backend/app/core/config.py` — pydantic `BaseSettings`, `env_prefix="ERP_"`, `.env` anchored at `backend/.env` (loads regardless of cwd) | Demo backend inherits the dev `backend/.env` (Mongo URI, **required** `ERP_JWT_SECRET`) automatically. |
| `docs_enabled` | `config.py` property → `env != "production"` | In `local`/`test`, `/docs` is on (needed for regression check #1). |
| Frontend API client | `frontend/src/shared/api.ts:7-9` — `API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api/v1"` | **Already** reads `VITE_API_BASE`. No `.ts` change needed — just build with `VITE_API_BASE=/api/v1`. |
| Frontend build | Vite; `npm run build` → `tsc --noEmit && vite build` → `frontend/dist/` (default `dist`, exists) | `BUILD_OUTPUT = frontend/dist`. |
| Frontend dev env | `frontend/.env` → `VITE_API_BASE=http://localhost:8000/api/v1` | Leave untouched so `npm run dev` keeps working. |
| gitignore | `.gitignore` already ignores `.env`, `.env.local`, `.env.production`, `dist/` | Add one line: `.env.demo`. |
| Scripts dir | `scripts/` (`seed_control_plane.py`, `provision_demo_tenant.py`) | New `scripts/share_demo.py` lands here; run from repo root. |

**Load-bearing fact to preserve (this codebase, and Starlette in general):**
> Middleware wraps **outermost-first — the LAST `add_middleware` call is the
> outermost wrapper and executes first per request.** (Stated verbatim in
> `main.py:94-98` and `docs/IP_ACCESS_CONTROL_PLAN.md §1`; `IPAccessMiddleware`,
> added last, is outermost today.) `Starlette.add_middleware` does
> `user_middleware.insert(0, …)`, so "added later" ⇒ "wraps more."
>
> **∴ To make the demo gate outermost — so an unauthenticated request is
> rejected before `IPAccess` / `RateLimit` / `CORS` / `AccessLog` run — the gate
> must be installed *after* the four existing `add_middleware` calls, i.e. LAST.**
> This is the **opposite** of the source spec's literal instruction ("add it
> first / before any other middleware"), which assumes append semantics. Getting
> this backwards is the single most likely way to ship this feature subtly broken.

---

## 2. Resolved placeholders (preflight, done)

| Spec placeholder | Resolved value |
|---|---|
| `<BACKEND_DIR>` (uvicorn cwd) | `backend` |
| FastAPI package dir | `backend/app` — so `demo_gate.py` lives at **`backend/app/demo_gate.py`**, imported `from app.demo_gate import …` |
| `<APP_IMPORT>` | `app.main:app` |
| `<APP_FILE>` | `backend/app/main.py` (**app-factory** `create_app`) |
| `<FRONTEND_DIR>` | `frontend` |
| `<BUILD_OUTPUT>` | `dist` (`frontend/dist`, exists) |
| `<API_PREFIX>` | `/api/v1` |
| health path (behind gate) | **`/health`** (root — already exists) |
| `parents[N]` in `main.py` for repo root | `parents[2]` (`backend/app/main.py` → `[0]`=app, `[1]`=backend, `[2]`=repo root) |
| `ROOT` in `scripts/share_demo.py` | `Path(__file__).resolve().parents[1]` |
| `TrustedHostMiddleware` | **absent** → source-spec Task 6 is **N/A** (no host-header fix needed) |
| `~/.cloudflared/config.yml` | **absent** (good — would block Quick Tunnels) |
| `cloudflared` on this machine | **NOT installed** → `brew install cloudflared` before the first live run (macOS + Homebrew both present) |

---

## 3. Hard constraints (carry forward from the source spec)

1. **No account / domain / DNS.** No `cloudflared login`, `cert.pem`, named tunnel,
   or `~/.cloudflared/config.yml`. Quick Tunnels are anonymous + ephemeral.
2. **Zero impact on normal dev.** With the demo not running, `uvicorn` /
   `npm run dev` are unchanged. Every new behavior gates behind env vars default OFF.
3. **No new runtime deps.** Python stdlib + FastAPI/Starlette only. Do **not** add
   `python-multipart`, `httpx`, `requests`, `rich`, `click`, etc.
4. **The gate covers everything** — API, `/docs`, `/redoc`, `/openapi.json`, and
   the mounted SPA. ⇒ **middleware**, never a `Depends`.
5. **Cross-platform.** One Python script; no `.sh` / `.ps1`.
6. **Secrets never committed.** Credentials live in `.env.demo` (gitignored).

---

## 4. Deliverables

```
scripts/share_demo.py            NEW   — the one command (stdlib only)
backend/app/demo_gate.py         NEW   — basic-auth middleware + SPA mount helper
backend/app/main.py              EDIT  — 1 import + 2 call sites (inside create_app)
.env.demo.example                NEW   — committed template
.gitignore                       EDIT  — append `.env.demo`
docs/DEMO_SHARING.md             NEW   — short operator runbook (analogous to IP_ACCESS_RUNBOOK.md)
```

`.env.demo` and `frontend/.env.production` are **generated** at runtime and are
**not** committed (both already gitignored — `.env.demo` after the edit above,
`.env.production` already).

---

## Task A — `backend/app/demo_gate.py` (middleware + mount helper)

> **The shipped `backend/app/demo_gate.py` is authoritative.** The listing below
> is the initial plan; verification added the **cookie handoff** (D-11) — the gate
> now admits a browser by an HttpOnly session cookie after its first Basic auth, so
> the app's own `Authorization: Bearer` JWT (post client-login) no longer collides
> with the gate's `Authorization: Basic` and re-triggers the browser prompt.

Opt-in; both functions no-op unless their env var is truthy, so importing/calling
them from the factory is free in normal dev.

```python
"""Opt-in HTTP Basic auth gate + SPA mount, used only when sharing a demo publicly.

Enabled solely by env vars (read raw here, NOT via ERP_-prefixed Settings, so the
demo surface never leaks into production config). Absent those vars, calling these
functions is a no-op, so normal local development is untouched.
"""
from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Scope

_TRUTHY = {"1", "true", "yes", "on"}


def _enabled(var: str) -> bool:
    return os.getenv(var, "").strip().lower() in _TRUTHY


class _SPAStaticFiles(StaticFiles):
    """StaticFiles that falls back to index.html for any unmatched path.

    The frontend uses BrowserRouter (real paths, not hash routing), so a client
    deep link or reload on e.g. /projects/123 arrives at the server as that path.
    Bare StaticFiles(html=True) serves index.html for "/" but 404s deep paths;
    this serves the SPA shell instead. Real asset requests still return the real
    file.
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
    add_middleware call) so it is the OUTERMOST wrapper — see
    docs/DEMO_SHARING_PLAN.md §1.
    """
    if not _enabled("DEMO_GATE_ENABLED"):
        return

    expected_user = os.environ["DEMO_GATE_USER"]
    expected_password = os.environ["DEMO_GATE_PASSWORD"]
    challenge = {"WWW-Authenticate": 'Basic realm="ERP Demo", charset="UTF-8"'}

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
    async def _demo_basic_auth(request: Request, call_next):
        import secrets  # local import keeps cost at zero when disabled

        user, password = _parse(request.headers.get("authorization", ""))
        user_ok = secrets.compare_digest(user, expected_user)
        password_ok = secrets.compare_digest(password, expected_password)
        if user_ok and password_ok:
            return await call_next(request)
        return Response(status_code=401, headers=challenge)


def mount_built_frontend(app: FastAPI, dist_dir: Path) -> None:
    """Serve the production React build from the same origin as the API.

    Must be called AFTER every API router is registered — a mount at "/" is greedy
    and shadows routes added after it. Uses _SPAStaticFiles so deep client-side
    routes fall back to index.html (docs/DEMO_SHARING_PLAN.md §A).
    """
    if not _enabled("SERVE_FRONTEND"):
        return
    if not dist_dir.is_dir():
        raise RuntimeError(
            f"SERVE_FRONTEND is on but the build directory does not exist: {dist_dir}"
        )
    app.mount("/", _SPAStaticFiles(directory=str(dist_dir), html=True), name="spa")
```

> **The source spec is wrong about `html=True`.** `StaticFiles(html=True)` serves
> `index.html` for `/` but returns **404** for unknown deep paths like
> `/projects/123` — it does **not** fall back to `index.html`. The frontend uses
> **BrowserRouter** (`frontend/src/App.tsx`), so a reload or shared deep link hits
> the server at that real path and would 404. `_SPAStaticFiles` fixes it by
> serving `index.html` on a 404 (verification check #6). Real assets still serve
> as real files; API routes still win because the mount is registered last.

---

## Task B — wire both calls into `create_app` (`backend/app/main.py`)

Two call sites, both **inside** `create_app`. One import.

**B1.** Add to the top imports (needs `Path` too — not currently imported):
```python
from pathlib import Path
...
from app.demo_gate import install_demo_gate, mount_built_frontend
```

**B2.** Install the gate **LAST**, immediately **after** the existing
`app.add_middleware(IPAccessMiddleware, cfg=cfg)` line (currently `main.py:106`),
so it becomes the outermost wrapper:
```python
    app.add_middleware(IPAccessMiddleware, cfg=cfg)

    # Opt-in demo gate (docs/DEMO_SHARING_PLAN.md). Installed LAST ⇒ OUTERMOST, so
    # an unauthenticated public request is rejected before IP filtering, rate
    # limiting, CORS, or access logging run. No-op unless DEMO_GATE_ENABLED is set,
    # so normal dev is byte-for-byte unchanged.
    install_demo_gate(app)
```

**B3.** Mount the built SPA **last**, right before `return app` (after the final
`app.include_router(projects_router)` at `main.py:153`):
```python
    app.include_router(projects_router)

    # Opt-in: serve the production React build from the API origin (same-origin ⇒
    # no CORS, works behind the tunnel). Greedy mount at "/" ⇒ MUST be last.
    # No-op unless SERVE_FRONTEND is set. (docs/DEMO_SHARING_PLAN.md)
    mount_built_frontend(app, Path(__file__).resolve().parents[2] / "frontend" / "dist")

    return app
```

> During build, print the resolved path once to confirm `parents[2]` →
> `<repo>/frontend/dist`.

---

## Task C — frontend origin-relative build (no `.ts` change)

`api.ts` **already** reads `VITE_API_BASE` (§1), so the only requirement is to
build the bundle with `VITE_API_BASE=/api/v1` (origin-relative) instead of the
`localhost:8000` dev fallback. The demo script owns this by generating
`frontend/.env.production` (Vite loads it only in `production` mode, so
`npm run dev` is unaffected):

```
VITE_API_BASE=/api/v1
```

`.env.production` is **already gitignored**, so it is generated by the script
(deterministic, survives a fresh clone) rather than committed. No edit to
`api.ts`, no edit to `frontend/.env`. See "Deviations" §D-1.

---

## Task D — `scripts/share_demo.py` (the one command)

> **The shipped `scripts/share_demo.py` is authoritative.** The listing below is
> the initial plan; verification surfaced two more fixes now in the real file:
> a **tunnel-edge readiness probe** (D-9) and **redirecting the backend's logs to
> `.demo-backend.log`** (D-10). Read the file for the final version.

Runnable from repo root, **stdlib only**. Full script below (adapted CONFIG +
`/health` readiness + `.env.production` generation; the rest is the source-spec
script verbatim). It: loads/creates `.env.demo` creds → generates
`frontend/.env.production` → `npm run build` → boots gated `uvicorn` (cwd
`backend`, import `app.main:app`) → waits for authenticated `/health` 200 →
opens `cloudflared` Quick Tunnel → waits for the edge to become routable → prints
the banner → cleans up on `Ctrl+C`.

```python
#!/usr/bin/env python3
"""Expose the locally running ERP to a client over a Cloudflare Quick Tunnel.

Starts a basic-auth-gated backend, opens an anonymous HTTPS tunnel, prints the
shareable URL and credentials, and shuts everything down on Ctrl+C.
"""
from __future__ import annotations

import argparse
import base64
import os
import re
import secrets
import shutil
import signal
import string
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------- CONFIG
ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
BUILD_OUTPUT = FRONTEND_DIR / "dist"
APP_IMPORT = "app.main:app"
HOST, PORT = "127.0.0.1", 8000
HEALTH_PATH = "/health"           # root route, NOT /api/v1/health
API_BASE_FOR_BUILD = "/api/v1"    # origin-relative base baked into the SPA build
ENV_FILE = ROOT / ".env.demo"
FRONTEND_PROD_ENV = FRONTEND_DIR / ".env.production"
# ------------------------------------------------------------------------

TUNNEL_URL_RE = re.compile(rb"https://[a-z0-9][a-z0-9-]*\.trycloudflare\.com")
_procs: list[subprocess.Popen] = []


def fail(message: str) -> None:
    print(f"\n  ERROR  {message}\n", file=sys.stderr)
    shutdown()
    sys.exit(1)


def preflight() -> None:
    """Fail fast on the two known Quick-Tunnel blockers."""
    if shutil.which("cloudflared") is None:
        fail(
            "cloudflared is not installed.\n"
            "         macOS:    brew install cloudflared\n"
            "         Windows:  winget install --id Cloudflare.cloudflared\n"
            "         Linux:    install the .deb from the cloudflared GitHub releases page"
        )
    if (Path.home() / ".cloudflared" / "config.yml").exists():
        fail(
            "~/.cloudflared/config.yml exists — it forces named-tunnel mode and "
            "breaks `cloudflared tunnel --url`. Rename it, then re-run."
        )


def load_or_create_credentials() -> tuple[str, str]:
    """Read .env.demo, generating a fresh password on first run."""
    if ENV_FILE.exists():
        values = {}
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
        user = values.get("DEMO_GATE_USER")
        password = values.get("DEMO_GATE_PASSWORD")
        if user and password:
            return user, password

    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for _ in range(24))
    user = "client"
    ENV_FILE.write_text(
        "# Generated by scripts/share_demo.py — gitignored, do not commit.\n"
        "# Delete this file to rotate the demo credentials.\n"
        f"DEMO_GATE_USER={user}\n"
        f"DEMO_GATE_PASSWORD={password}\n",
        encoding="utf-8",
    )
    return user, password


def ensure_prod_env() -> None:
    """Bake an origin-relative API base into the production build.

    api.ts falls back to http://localhost:8000/api/v1, which breaks behind the
    tunnel. .env.production is gitignored, so we (re)generate it every run.
    """
    FRONTEND_PROD_ENV.write_text(
        f"VITE_API_BASE={API_BASE_FOR_BUILD}\n", encoding="utf-8"
    )


def build_frontend() -> None:
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm is None:
        fail("npm not found on PATH — cannot build the frontend.")
    ensure_prod_env()
    print("  ->  Building the production frontend bundle (this takes a minute)…")
    result = subprocess.run([npm, "run", "build"], cwd=FRONTEND_DIR)
    if result.returncode != 0:
        fail("Frontend build failed. Fix the build, then re-run.")
    if not BUILD_OUTPUT.is_dir():
        fail(f"Build reported success but {BUILD_OUTPUT} does not exist.")


def start_backend(user: str, password: str) -> subprocess.Popen:
    env = {
        **os.environ,
        "DEMO_GATE_ENABLED": "1",
        "DEMO_GATE_USER": user,
        "DEMO_GATE_PASSWORD": password,
        "SERVE_FRONTEND": "1",
    }
    cmd = [
        sys.executable, "-m", "uvicorn", APP_IMPORT,
        "--host", HOST, "--port", str(PORT),
        "--proxy-headers", "--forwarded-allow-ips", "*",
    ]
    print("  ->  Starting the gated backend…")
    return subprocess.Popen(cmd, cwd=BACKEND_DIR, env=env)


def wait_for_backend(user: str, password: str, timeout: int = 60) -> None:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    request = urllib.request.Request(
        f"http://{HOST}:{PORT}{HEALTH_PATH}",
        headers={"Authorization": f"Basic {token}"},
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                if response.status == 200:
                    print("  ->  Backend is up and the gate is active.")
                    return
        except (urllib.error.URLError, urllib.error.HTTPError, OSError):
            time.sleep(1)
    fail(f"Backend did not become healthy within {timeout}s "
         "(is MongoDB running? /health returns 503 until it is).")


def start_tunnel() -> tuple[subprocess.Popen, str]:
    print("  ->  Opening the Cloudflare Quick Tunnel…")
    process = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", f"http://{HOST}:{PORT}", "--no-autoupdate"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,   # cloudflared logs the URL on stderr
        bufsize=0,
    )
    url_box: dict[str, str] = {}

    def reader() -> None:
        for raw in iter(process.stdout.readline, b""):
            if "url" not in url_box:
                match = TUNNEL_URL_RE.search(raw)
                if match:
                    url_box["url"] = match.group(0).decode()

    threading.Thread(target=reader, daemon=True).start()

    deadline = time.time() + 45
    while time.time() < deadline:
        if "url" in url_box:
            return process, url_box["url"]
        if process.poll() is not None:
            fail("cloudflared exited before producing a URL.")
        time.sleep(0.5)
    fail("Timed out waiting for a trycloudflare.com URL.")


def banner(url: str, user: str, password: str) -> None:
    line = "=" * 68
    print(
        f"\n{line}\n"
        f"  DEMO IS LIVE — send this to the client\n"
        f"{line}\n\n"
        f"  URL       {url}\n"
        f"  Username  {user}\n"
        f"  Password  {password}\n\n"
        f"  Send the URL and the password over two different channels.\n"
        f"  This URL is temporary and changes every time you run this script.\n"
        f"  The demo dies when this terminal closes or the laptop sleeps.\n\n"
        f"  Press Ctrl+C to stop sharing.\n"
        f"{line}\n"
    )


def shutdown(*_args) -> None:
    for process in reversed(_procs):
        if process.poll() is None:
            process.terminate()
    deadline = time.time() + 10
    for process in _procs:
        remaining = max(0, deadline - time.time())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            process.kill()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true",
                        help="reuse the existing frontend build")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, lambda *a: (shutdown(), sys.exit(0)))

    preflight()
    user, password = load_or_create_credentials()
    if not args.skip_build:
        build_frontend()
    elif not BUILD_OUTPUT.is_dir():
        fail("--skip-build was passed but no existing build was found.")

    _procs.append(start_backend(user, password))
    wait_for_backend(user, password)
    tunnel, url = start_tunnel()
    _procs.append(tunnel)
    banner(url, user, password)

    try:
        while all(p.poll() is None for p in _procs):
            time.sleep(1)
        print("\n  A child process exited. Shutting down.")
    finally:
        shutdown()


if __name__ == "__main__":
    main()
```

> **`/health` already exists** (`main.py:108`) — source-spec Task 7's "create the
> route if missing" is N/A. It sits behind the gate, which is why the readiness
> probe sends credentials. It also pings Mongo, so the demo requires the local
> Mongo to be up (the timeout message says so).

---

## Task E — supporting files

**`.env.demo.example`** (committed template):
```
DEMO_GATE_USER=client
DEMO_GATE_PASSWORD=replace-me-or-delete-this-file-to-autogenerate
```

**`.gitignore`** — append under the "Env & secrets" block:
```
.env.demo
```

**`docs/DEMO_SHARING.md`** — short operator runbook (sibling to
`docs/IP_ACCESS_RUNBOOK.md`): one-line install of `cloudflared`; how to run
(`python scripts/share_demo.py`, `--skip-build`); what to send the client and to
**split URL + password across two channels**; that the URL is ephemeral and dies
with the terminal / on sleep; how to **rotate** creds (delete `.env.demo`,
re-run); the "rename `~/.cloudflared/config.yml`" gotcha; and the reminder that
**Mongo must be running** and this is a demo tool, **not** hosting.

---

## Task F — Verification (run all; record each result)

| # | Check | Command | Expected |
|---|---|---|---|
| 1 | **Regression** — gate invisible when off | (no demo env) start app, `curl -i localhost:8000/docs` | **200** as today |
| 2 | **Gate on** | `python scripts/share_demo.py`, then `curl -i http://127.0.0.1:8000/docs` | **401** + `WWW-Authenticate: Basic` |
| 3 | **Gate accepts** | `curl -i -u client:<pw> http://127.0.0.1:8000/health` | **200** |
| 4 | **Static gated** (catches the mount-bypass bug — do not skip) | `curl -i http://127.0.0.1:8000/` | **401**, not `index.html` |
| 5 | **Tunnel works** | `curl -i -u client:<pw> <printed-url>/health` | **200** from outside |
| 6 | **SPA deep link** | `curl -u client:<pw> <printed-url>/some/deep/route` | `index.html` body, not 404 |
| 7 | **Teardown** | `Ctrl+C`, then `ps` for `uvicorn`/`cloudflared` | no orphans |
| 8 | **Idempotence** | re-run the script | reuses `.env.demo` creds (no new password) |

**On this machine, check 5 (and the via-tunnel half of check 6) is blocked until
`brew install cloudflared`; check 6's SPA fallback is verified locally.**
Checks 1–4, 7, 8 need only `npm` + Mongo and can be done immediately. During the
build phase, also run `cloudflared --version` and report it (currently: not
installed).

---

## Sequencing (single session)

This is small, isolated, and opt-in — build it in one sitting, in this order:

1. **Task A** — `demo_gate.py`.
2. **Task B** — wire the two call sites; print the resolved `dist` path once.
3. **Task C + E** — `.gitignore`, `.env.demo.example`, runbook (Task C is owned by
   the script, so nothing to edit besides confirming `api.ts` already reads
   `VITE_API_BASE`).
4. **Task D** — `share_demo.py`.
5. **Task F** — verification. Do checks **1–4, 7, 8** now. Note **5, 6** need
   `cloudflared` (offer to `brew install cloudflared`, or leave to the operator).
6. Commit at the boundary (confirm first — see `[[blyns-git-remote-workflow]]`).

No backend/frontend tests are strictly required (opt-in, off by default, no
change to existing behavior), but a **regression assertion** that `create_app()`
with no demo env vars adds **no** extra middleware and **no** `/` mount is cheap
insurance and is worth adding under `backend/tests/`.

---

## Known gotchas — handle, don't rediscover

- **Middleware order is inverted vs. the source spec.** Gate goes **last**
  (outermost). See §1. This is the big one.
- **Mount greediness.** `mount_built_frontend` at `/` shadows anything registered
  after it — it goes **last**, after every `include_router`. `/health`, `/docs`,
  `/openapi.json`, and `/api/v1/*` are all registered earlier, so they still win.
- **`~/.cloudflared/config.yml` blocks Quick Tunnels.** The script's `preflight()`
  checks for it and tells the operator to rename it. (Absent today.)
- **cloudflared logs the URL to stderr.** The script merges stdout+stderr; never
  parse stdout alone.
- **Random URL per run.** Quick Tunnels are ephemeral by design — no way to pin
  the hostname without an account + domain. Never bake the URL anywhere.
- **`--proxy-headers` × `IPAccessMiddleware`.** With proxy headers on, authenticated
  tunnel requests are evaluated against IP rules using the **forwarded** client IP.
  In `local`/`test` **no IP rules are seeded** (seeding is production-only) and the
  filter is default-allow, so this is a non-issue. **Do not run the demo against
  production IP config**, and if you've hand-seeded restrictive rules locally, the
  `ip_filter_enabled` kill switch (`config.py`) is the escape hatch.
- **Mongo must be up.** `/health` returns 503 until Mongo answers, so the readiness
  probe (and the demo) won't come alive without the local DB running.
- **Don't proxy MongoDB.** Nothing here touches the DB port; Mongo stays on
  `127.0.0.1`.
- **Quick Tunnels have no SLA** — fine for demos, not a hosting strategy.

---

## Deviations from the source spec (intentional)

- **D-1 — Middleware placement is reversed.** Source Task 3 says install the gate
  *before* other middleware; this codebase's `add_middleware` uses `insert(0)`, so
  **last = outermost**. We install it **after** the four existing middlewares.
  Same *intent* (gate outermost), correct *mechanism* for this repo. (§1, §B2)
- **D-2 — App factory, not a flat app.** `main.py` builds the app in
  `create_app(cfg)`. Both calls are wired **inside** the factory (gate after the
  middleware block; mount before `return app`), not at module top/bottom. (§B)
- **D-3 — Health path is `/health`, not `<API_PREFIX>/health`.** A root `/health`
  already exists and pings Mongo. Source Task 7's "create the route" is skipped;
  the readiness probe and verification checks use `/health`. (§1, §D)
- **D-4 — `demo_gate.py` lives at `backend/app/demo_gate.py`** (inside the `app`
  package), not `backend/demo_gate.py`, so it imports as `from app.demo_gate …`
  like every other module and stays importable regardless of cwd. (§2, §A)
- **D-5 — Origin-relative frontend via generated `.env.production`, no `.ts`
  edit.** `api.ts` already reads `VITE_API_BASE`; source Task 5's code change is
  unnecessary. Because `.env.production` is gitignored, the script **generates** it
  each run (deterministic, fresh-clone-safe) rather than committing it. (§C, §D)
- **D-6 — Task 6 (TrustedHostMiddleware) dropped.** None is installed, so no
  host-header fix and no `ALLOWED_HOSTS` env var (the source script set it; it
  would be inert here). CORS is also moot — the SPA is served **same-origin**. (§2)
- **D-7 — `preflight()` added to the script.** Folds the `cloudflared`-missing and
  `config.yml`-present checks (source Task 1 + a gotcha) into one fail-fast step at
  startup instead of scattering them.
- **D-8 — SPA deep-link fallback (`_SPAStaticFiles`), not bare `StaticFiles`.**
  Found during verification (check #6): `StaticFiles(html=True)` 404s deep
  BrowserRouter paths; the source spec's claim that it "falls back to index.html"
  is wrong. `mount_built_frontend` uses a `StaticFiles` subclass that serves
  `index.html` on 404. See Task A. Locked in by
  `backend/tests/integration/test_demo_gate.py`.
- **D-9 — tunnel-edge readiness probe (`wait_for_tunnel`).** A Quick Tunnel prints
  its URL several seconds (sometimes ~a minute) before Cloudflare's edge can route
  to the origin; a request in that window is reset. The script now probes the
  PUBLIC url with credentials until it returns 200, then prints the banner — so the
  URL handed to the client works on first click. Non-fatal soft fallback on
  timeout (120s). Found during verification check #5.
- **D-10 — backend logs redirected to `.demo-backend.log`.** `start_backend` was
  inheriting the console, so the backend's (DEBUG-level) `pymongo` output flooded
  the terminal AND interleaved into — corrupting — the printed banner URL. Now the
  child's stdout/stderr go to a gitignored `.demo-backend.log`; the console shows
  only the script's progress + a clean banner. Found during verification.
- **D-11 — session-cookie handoff (fixes the post-login re-prompt).** The gate
  authenticates on the `Authorization` header, but the ERP app reuses that header
  for its Bearer JWT once a client logs in — so the SPA's `Authorization: Bearer`
  calls were seen by the gate as "not Basic" → `401 + WWW-Authenticate: Basic` →
  the browser re-popped the password prompt while the portal failed in the
  background. The gate now pins an HttpOnly, SameSite=Lax session cookie
  (`erp_demo_gate`, value = sha256 of the creds, constant-time compared) on the
  first successful Basic auth, and admits later requests by that cookie regardless
  of the Authorization header. A Bearer request WITHOUT the cookie is still
  challenged. Reported by the user after their first live test; locked in by two
  tests in `test_demo_gate.py`.

---

## Build status (2026-08-03) — BUILT

All deliverables shipped and **all 9 verification checks PASS**. `cloudflared`
2026.7.3 installed; the live public tunnel was exercised end-to-end (check 5:
`https://…trycloudflare.com/health` +creds → 200, no-creds → 401; check 6: deep
route → index.html; check 7: clean teardown; check 8: creds reused). Automated
`backend/tests/integration/test_demo_gate.py` → 9/9 green; the middleware/config
regression batch → 18/18. Four fixes found during verification: D-8 (SPA
fallback), D-9 (tunnel readiness probe), D-10 (backend log redirect), D-11
(session-cookie handoff — post-login re-prompt).
