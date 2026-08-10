"""FastAPI app factory + router mounting (docs/ARCHITECTURE.md, ENVIRONMENTS.md).

Behavior differences between local / test / production are driven ONLY by
Settings (env vars): docs on/off, CORS origins, rate limiting. Module routers
are mounted here as each build phase lands.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.control_plane.ip_access.middleware import IPAccessMiddleware
from app.core.config import Settings, validate_for_production
from app.core.config import settings as default_settings
from app.core.db import close_db_manager, get_db_manager, init_db_manager
from app.core.errors import register_exception_handlers
from app.core.logging import AccessLogMiddleware, configure_logging
from app.core.rate_limit import RateLimitMiddleware
from app.demo_gate import install_demo_gate, mount_built_frontend
from app.shared.schemas import envelope

try:
    APP_VERSION = version("erp-backend")
except PackageNotFoundError:  # running from a raw checkout
    APP_VERSION = "0.0.0-dev"


def create_app(cfg: Settings | None = None) -> FastAPI:
    cfg = cfg or default_settings

    # Hardening (docs/ENVIRONMENTS.md §4/§6): a production process must not start
    # with a dev secret, open docs, or localhost origins. No-op elsewhere.
    validate_for_production(cfg)
    configure_logging(cfg)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = init_db_manager(cfg.mongo_uri)
        app.state.db = db

        # Rate-limit collections (accounting + enforcement) need their indexes
        # before the middleware writes to them (docs/ARCHITECTURE.md §6). Both
        # create_index calls are idempotent, so every worker can run them.
        from app.control_plane.discovery_bookings.repository import (
            ensure_discovery_booking_indexes,
        )
        from app.control_plane.ip_access.repository import ensure_ip_rule_indexes
        from app.core.rate_limit import (
            ensure_bucket_indexes,
            ensure_enforcement_indexes,
        )

        try:
            await ensure_bucket_indexes(db.control)
            await ensure_enforcement_indexes(db.control)
            await ensure_ip_rule_indexes(db.control)
            await ensure_discovery_booking_indexes(db.control)
        except Exception:  # index setup must not stop the app from serving
            pass

        # In-process metrics collector loop (docs/ADMIN_PORTAL.md §4 perf
        # note): rolling snapshots so the dashboard never fans out live.
        collector_task: asyncio.Task | None = None
        if cfg.metrics_interval_sec > 0:
            from app.control_plane.metrics.collector import collect_platform_metrics

            async def _collect_loop() -> None:
                while True:
                    await asyncio.sleep(cfg.metrics_interval_sec)
                    try:
                        await collect_platform_metrics(db)
                    except Exception:  # collector must never kill the app
                        pass

            collector_task = asyncio.create_task(_collect_loop())

        yield

        if collector_task is not None:
            collector_task.cancel()
        close_db_manager()

    app = FastAPI(
        title="ERP",
        version=APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs" if cfg.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if cfg.docs_enabled else None,
    )

    register_exception_handlers(app)

    # Middleware wraps outermost-first — the LAST add_middleware call is the
    # outermost wrapper and runs first per request. The IP access filter fronts
    # even the rate limiter, so a blocked IP is rejected before it can consume a
    # rate-limit slot; then rate limiting (reject floods before any work), CORS,
    # and the access log closest to the app so it records the true handler status.
    app.add_middleware(AccessLogMiddleware, cfg=cfg)
    app.add_middleware(CORSMiddleware,
                       allow_origins=cfg.cors_origins,
                       allow_credentials=True,
                       allow_methods=["*"],
                       allow_headers=["*"])
    app.add_middleware(RateLimitMiddleware, cfg=cfg)
    app.add_middleware(IPAccessMiddleware, cfg=cfg)

    # Opt-in demo gate (docs/DEMO_SHARING_PLAN.md). Installed LAST ⇒ OUTERMOST, so
    # an unauthenticated public request is rejected before IP filtering, rate
    # limiting, CORS, or access logging run. No-op unless DEMO_GATE_ENABLED is set,
    # so normal dev is byte-for-byte unchanged.
    install_demo_gate(app)

    @app.get("/health")
    async def health():
        try:
            mongo_ok = await get_db_manager().ping()
        except Exception:
            mongo_ok = False
        body = envelope(
            {
                "status": "ok" if mongo_ok else "degraded",
                "mongo": mongo_ok,
                "env": cfg.env,
                "version": APP_VERSION,
            }
        )
        if not mongo_ok:
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=503, content=body)
        return body

    # --- module routers (mounted as phases land) ---
    from app.auth.admin_auth import router as admin_auth_router
    from app.auth.client_auth import router as client_auth_router
    from app.control_plane.admin_users.router import router as admin_users_router
    from app.control_plane.companies.router import router as companies_router
    from app.control_plane.discovery_bookings.router import (
        public_router as discovery_public_router,
    )
    from app.control_plane.discovery_bookings.router import (
        router as discovery_admin_router,
    )
    from app.control_plane.ip_access.router import router as ip_rules_router
    from app.control_plane.metrics.router import router as metrics_router
    from app.modules.crm.router import router as crm_router
    from app.modules.dashboard.router import router as dashboard_router
    from app.modules.finance.router import router as finance_router
    from app.modules.inventory.router import router as inventory_router
    from app.modules.production.router import router as production_router
    from app.modules.projects.router import router as projects_router
    from app.modules.settings.router import router as settings_router

    app.include_router(admin_auth_router)
    app.include_router(client_auth_router)
    app.include_router(companies_router)
    app.include_router(admin_users_router)
    app.include_router(ip_rules_router)
    app.include_router(discovery_admin_router)
    app.include_router(discovery_public_router)
    app.include_router(metrics_router)
    app.include_router(dashboard_router)
    app.include_router(settings_router)
    app.include_router(crm_router)
    app.include_router(inventory_router)
    app.include_router(finance_router)
    app.include_router(projects_router)
    app.include_router(production_router)

    # Opt-in: serve the production React build from the API origin (same-origin ⇒
    # no CORS, works behind the tunnel). Greedy mount at "/" ⇒ MUST be last.
    # No-op unless SERVE_FRONTEND is set (docs/DEMO_SHARING_PLAN.md).
    mount_built_frontend(app, Path(__file__).resolve().parents[2] / "frontend" / "dist")

    return app


app = create_app()
